import datetime
import json
from peewee import Proxy, chunked
from playhouse.apsw_ext import *
from playhouse.sqlite_ext import JSONField
from playhouse.migrate import *


class KyogreDB:
    _db = Proxy()
    _migrator = None
    @classmethod
    def start(cls, db_path):
        handle = APSWDatabase(db_path, pragmas={
            'journal_mode': 'wal',
            'cache_size': -1 * 64000,
            'foreign_keys': 1,
            'ignore_check_constraints': 0
        })
        cls._db.initialize(handle)
        # ensure db matches current schema
        cls._db.create_tables([
            AutoBadgeTable, BadgeAssignmentTable, BadgeTable, EventTable, GuildTable, GymTable,
            HideoutTable, InvasionTable, InviteRoleTable, LocationNoteTable, LocationRegionRelation,
            LocationTable, LureTable, LureTypeRelation, LureTypeTable,
            PokemonTable, PokestopTable, QuestTable, RaidActionTable,
            RaidBossRelation, RaidTable, RegionTable, ResearchTable,
            RewardTable, SightingTable, SilphcardTable, SubscriptionTable,
            TeamTable, TradeTable, TrainerReportRelation, TrainerTable,
            TopSubsTable, APIUsageTable
        ])
        cls.init()
        cls._migrator = SqliteMigrator(cls._db)

    @classmethod
    def stop(cls):
        return cls._db.close()
    
    @classmethod
    def init(cls):
        # check team
        try:
            TeamTable.get()
        except:
            TeamTable.reload_default()
        # check pokemon
        try:
            PokemonTable.get()
        except:
            PokemonTable.reload_default()
        # check regions
        try:
            RegionTable.get()
        except:
            RegionTable.reload_default()
        # check locations
        try:
            LocationTable.get()
        except:
            LocationTable.reload_default()
        # check quests
        try:
            QuestTable.get()
        except:
            QuestTable.reload_default()
        try:
            LureTypeTable.get()
        except:
            LureTypeTable.reload_default()


class BaseModel(Model):
    class Meta:
        database = KyogreDB._db


class TeamTable(BaseModel):
    name = TextField(unique=True)
    emoji = TextField()

    @classmethod
    def reload_default(cls):
        if not KyogreDB._db:
            return
        try:
            cls.delete().execute()
        except:
            pass
        with open('config.json', 'r') as f:
            team_data = json.load(f)['team_dict']
        for name, emoji in team_data.items():
            cls.insert(name=name, emoji=emoji).execute()


class GuildTable(BaseModel):
    snowflake = BigIntegerField(unique=True)
    config_dict = JSONField(null=True)


class TrainerTable(BaseModel):
    snowflake = BigIntegerField(index=True)
    team = ForeignKeyField(TeamTable, backref='trainers', null=True)
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='trainers')

    class Meta:
        constraints = [SQL('UNIQUE(snowflake, guild_id)')]


class PokemonTable(BaseModel):
    id = IntegerField(primary_key=True)
    name = TextField(index=True)
    legendary = BooleanField()
    mythical = BooleanField()
    shiny = BooleanField()
    alolan = BooleanField()
    galarian = BooleanField()
    types = JSONField()
    released = BooleanField(index=True)
    attack = IntegerField()
    defense = IntegerField()
    stamina = IntegerField()

    @classmethod
    def reload_default(cls):
        if not KyogreDB._db:
            return
        try:
            cls.delete().execute()
        except:
            pass
        with open('data/pkmn_data.json', 'r') as f:
            pkmn_data = json.load(f)
        with KyogreDB._db.atomic():
            for chunk in chunked(pkmn_data, 50):
                cls.insert_many(chunk).execute()


class SilphcardTable(BaseModel):
    trainer = BigIntegerField(index=True)
    name = TextField(index=True)
    url = TextField(unique=True)


class RegionTable(BaseModel):
    name = TextField(index=True)
    area = TextField(null=True)
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='regions', index=True)

    @classmethod
    def reload_default(cls):
        if not KyogreDB._db:
            return
        try:
            cls.delete().execute()
        except:
            pass
        with open('data/region_data.json', 'r') as f:
            region_data = json.load(f)
        with KyogreDB._db.atomic():
            for region in region_data:
                try:
                    if 'guild' in region and region['guild']:
                        for guild_id in region['guild'].split(','):
                            guild, __ = GuildTable.get_or_create(snowflake=guild_id)
                            RegionTable.create(name=region['name'], area=None, guild=guild)
                except Exception as e:
                    print(e)
    
    class Meta:
        constraints = [SQL('UNIQUE(name, guild_id)')]


class LocationTable(BaseModel):
    id = AutoField()
    name = TextField(index=True)
    latitude = TextField()
    longitude = TextField()
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='locations', index=True)

    class Meta:
        constraints = [SQL('UNIQUE(name, latitude, longitude, guild_id)')]

    @classmethod
    def create_location(ctx, name, data):
        try:
            latitude, longitude = data['coordinates'].split(',')
            if 'guild' in data and data['guild']:
                for guild_id in data['guild'].split(','):
                    with KyogreDB._db.atomic():
                        guild, __ = GuildTable.get_or_create(snowflake=guild_id)
                        location = LocationTable.create(name=name, latitude=latitude, longitude=longitude, guild=guild)
                        if 'region' in data and data['region']:
                            for region_name in data['region'].split(','):
                                with KyogreDB._db.atomic():
                                    # guild_id used here because peewee will not get correctly if obj used and throw error
                                    region, __ = RegionTable.get_or_create(name=region_name, area=None, guild=guild_id)
                                    LocationRegionRelation.create(location=location, region=region)
                        if 'notes' in data:
                            for note in data['notes']:
                                if note:
                                    LocationNoteTable.create(location=location, note=note)
                        if 'ex_eligible' in data:
                            GymTable.create(location=location, ex_eligible=data['ex_eligible'])
                        else:
                            PokestopTable.create(location=location)
        except Exception as e:
            print(e)

    @classmethod
    def create_single_location(ctx, name, data, guild_id):
        try:
            latitude, longitude = data['coordinates'].split(',')
            if 'guild' in data and data['guild']:
                with KyogreDB._db.atomic():
                    guild, __ = GuildTable.get_or_create(snowflake=guild_id)
                    location = LocationTable.create(name=name, latitude=latitude, longitude=longitude, guild=guild)
                    if 'region' in data and data['region']:
                        for region_name in data['region'].split(','):
                            with KyogreDB._db.atomic():
                                # guild_id used here because peewee will not get correctly if obj used and throw error
                                region, __ = RegionTable.get_or_create(name=region_name, area=None, guild=guild_id)
                                LocationRegionRelation.create(location=location, region=region)
                    if 'notes' in data:
                        for note in data['notes']:
                            if note:
                                LocationNoteTable.create(location=location, note=note)
                    if 'ex_eligible' in data:
                        location_id = GymTable.create(location=location, ex_eligible=data['ex_eligible'])
                    else:
                        location_id = PokestopTable.create(location=location)
                    return location_id, None
        except Exception as e:
            return None, e

    @classmethod
    def reload_default(cls):
        if not KyogreDB._db:
            return
        try:
            cls.delete().execute()
        except:
            pass
        with open('data/gym_data.json', 'r') as f:
            gym_data = json.load(f)
        with open('data/pokestop_data.json', 'r') as f:
            pokestop_data = json.load(f)
        for name, data in gym_data.items():
            LocationTable.create_location(name, data)
        for name, data in pokestop_data.items():
            LocationTable.create_location(name, data)


class LocationNoteTable(BaseModel):
    location = ForeignKeyField(LocationTable, backref='notes')
    note = TextField()


class LocationRegionRelation(BaseModel):
    location = ForeignKeyField(LocationTable, backref='regions')
    region = ForeignKeyField(RegionTable, backref='locations')


class PokestopTable(BaseModel):
    location = ForeignKeyField(LocationTable, backref='pokestops', primary_key=True)


class GymTable(BaseModel):
    location = ForeignKeyField(LocationTable, backref='gyms', primary_key=True)
    ex_eligible = BooleanField(index=True)


class TrainerReportRelation(BaseModel):
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='reports', index=True)
    id = AutoField()
    created = BigIntegerField(index=True)
    trainer = BigIntegerField(index=True)
    location = ForeignKeyField(LocationTable, index=True, null=True)
    message = BigIntegerField(index=True, null=True)
    updated = DateTimeField()
    cancelled = TextField()


class QuestTable(BaseModel):
    name = TextField()
    reward_pool = JSONField()

    @classmethod
    def reload_default(cls):
        if not KyogreDB._db:
            return
        try:
            cls.delete().execute()
        except:
            pass
        with open('data/quest_data.json', 'r') as f:
            quest_data = json.load(f)
        with KyogreDB._db.atomic():
            for quest in quest_data:
                try:
                    name = quest['name']
                    pool = quest['reward_pool']
                    QuestTable.create(name=name, reward_pool=pool)
                    parse_reward_pool(pool)
                except Exception as e:
                    print(e)


class ResearchTable(BaseModel):
    trainer_report = ForeignKeyField(TrainerReportRelation, backref='research')
    quest = TextField(index=True)
    reward = TextField()


class LureInstance:
    def __init__(self, created, location_name, lure_type, latitude, longitude):
        self.created = created
        self.location_name = location_name
        self.lure_type = lure_type
        self.latitude = latitude
        self.longitude = longitude


class Lure:
    def __init__(self, name):
        self.name = name


class LureTypeTable(BaseModel):
    name = TextField()

    @classmethod
    def reload_default(cls):
        for lure_type in ['normal', 'glacial', 'mossy', 'magnetic']:
            LureTypeTable.create(name=lure_type)


class LureTable(BaseModel):
    trainer_report = ForeignKeyField(TrainerReportRelation, backref='lure')


class LureTypeRelation(BaseModel):
    lure = ForeignKeyField(LureTable, backref='lure')
    type = ForeignKeyField(LureTypeTable, backref='lure')


class InvasionInstance:
    def __init__(self, id, created, location_name, pokemon, latitude, longitude):
        self.id=id
        self.created=created
        self.location_name=location_name
        self.pokemon=pokemon
        self.latitude=latitude
        self.longitude=longitude


class InvasionTable(BaseModel):
    trainer_report = ForeignKeyField(TrainerReportRelation, backref='invasion')
    pokemon_number = ForeignKeyField(PokemonTable, null=True, backref='invasion')


class HideoutInstance:
    def __init__(self, id, created, location_id, location_name, leader, first_pokemon,
                 second_pokemon, third_pokemon, latitude, longitude, message, trainer):
        self.id = id
        self.created = created
        self.location_id = location_id
        self.location_name = location_name
        self.leader = leader
        self.first_pokemon = first_pokemon
        self.second_pokemon = second_pokemon
        self.third_pokemon = third_pokemon
        self.latitude = latitude
        self.longitude = longitude
        self.message = message
        self.trainer = trainer


class HideoutTable(BaseModel):
    trainer_report = ForeignKeyField(TrainerReportRelation, backref='invasion')
    rocket_leader = TextField(null=True)
    first_pokemon = TextField(null=True)
    second_pokemon = TextField(null=True)
    third_pokemon = TextField(null=True)


def parse_reward_pool(pool):
    for key, val in pool["items"].items():
        try:
            RewardTable.create(name=key.lower())
        except Exception as e:
            pass


class Reward:
    def __init__(self, name, quantity):
        self.name = name
        self.quantity = quantity


class RewardTable(BaseModel):
    name = TextField(index=True, unique=True)
    quantity = IntegerField(null=True)


class SightingTable(BaseModel):
    trainer_report = ForeignKeyField(TrainerReportRelation, backref='sightings')
    pokemon = ForeignKeyField(PokemonTable, backref='sightings')


class BossTable(BaseModel):
    pokemon = TextField(index=True)
    level = TextField(index=True)


class RaidTable(BaseModel):
    trainer_report = ForeignKeyField(TrainerReportRelation, backref='raids')
    level = TextField(index=True, null=True)
    pokemon = TextField(index=True, null=True)
    hatch_time = DateTimeField(index=True, null=True)
    expire_time = DateTimeField(index=True, null=True)
    channel = BigIntegerField(index=True)
    weather = TextField(index=True, null=True)


class RaidActionTable(BaseModel):
    raid = ForeignKeyField(RaidTable, backref='raid_action')
    action = TextField(index=True)
    action_time = DateTimeField(index=True)
    trainer_dict = JSONField(null=True)


class RaidBossRelation(BaseModel):
    boss = ForeignKeyField(BossTable, backref='raids')
    raid = ForeignKeyField(RaidTable, backref='boss')


class SubscriptionTable(BaseModel):
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='events', index=True)
    trainer = BigIntegerField(index=True)
    type = TextField(index=True)
    target = TextField(index=True)
    specific = TextField(index=True, null=True)

    class Meta:
        constraints = [SQL('UNIQUE(trainer, type, target, specific)')]


class TopSubsTable(BaseModel):
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='events', index=True)
    pokemon = TextField(index=True)
    type = TextField()
    count = IntegerField()


class TradeTable(BaseModel):
    trainer = BigIntegerField(index=True)
    channel = BigIntegerField()
    offer = TextField()
    wants = TextField()


class InviteRoleTable(BaseModel):
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='inviteroles', index=True)
    invite = TextField(index=True)
    role = BigIntegerField(index=True)

    class Meta:
        constraints = [SQL('UNIQUE(guild_id, invite)')]


class EventTable(BaseModel):
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='events', index=True)
    eventname = TextField(index=True)
    active = BooleanField()
    role = BigIntegerField(index=True)

    class Meta:
        constraints = [SQL('UNIQUE(guild_id, eventname)')]


class BadgeTable(BaseModel):
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='badges', index=True)
    name = TextField(index=True)
    description = TextField()
    emoji = BigIntegerField(index=True)
    active = BooleanField()
    message = BigIntegerField(index=True, null=True)

    class Meta:
        constraints = [SQL('UNIQUE(name, description, emoji)')]


class BadgeAssignmentTable(BaseModel):
    trainer = BigIntegerField(index=True)
    badge = ForeignKeyField(BadgeTable, field=BadgeTable.id, backref='badgeassignment', index=True)

    class Meta:
        constraints = [SQL('UNIQUE(trainer, badge_id)')]


class AutoBadgeTable(BaseModel):
    guild = ForeignKeyField(GuildTable, field=GuildTable.snowflake, backref='autobadge', index=True)
    stat = TextField()
    threshold = IntegerField()
    badge = IntegerField()

    class Meta:
        constraints = [SQL('UNIQUE(guild_id, stat, threshold, badge)')]


class APIUsageTable(BaseModel):
    trainer = ForeignKeyField(TrainerTable, field=TrainerTable.id, backref='APIUsage', index=True)
    date = DateField(formats='%Y-%m-%d', default=datetime.datetime.now)

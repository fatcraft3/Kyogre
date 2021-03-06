import copy
import datetime
import discord

from kyogre import server_emoji, utils
from kyogre.exts.pokemon import Pokemon


async def get_embed_field_indices(embed):
    index = 0
    embed_indices = {"gym": None,
                    "possible": None,
                    "interest": None,
                    "times": None,
                    "status": None,
                    "team": None,
                    "details": None,
                    "weak": None,
                    "maybe": None,
                    "coming": None,
                    "here": None,
                    "tips": None,
                    "directions": None
                    }
    for field in embed.fields:
        if "gym" in field.name.lower():
            embed_indices["gym"] = index
        if "possible" in field.name.lower():
            embed_indices["possible"] = index
        if "interest" in field.name.lower():
            embed_indices["interest"] = index
        if "times" in field.name.lower():
            embed_indices["times"] = index
        if "status" in field.name.lower():
            embed_indices["status"] = index
        if "team" in field.name.lower():
            embed_indices["team"] = index
        if "details" in field.name.lower():
            embed_indices["details"] = index
        if "weak" in field.name.lower():
            embed_indices["weak"] = index
        if "tips" in field.name.lower():
            embed_indices["tips"] = index
        if "maybe" in field.name.lower():
            embed_indices["maybe"] = index
        if "coming" in field.name.lower():
            embed_indices["coming"] = index
        if "here" in field.name.lower():
            embed_indices["here"] = index
        if "directions" in field.name.lower():
            embed_indices["directions"] = index
        # if "" in field.name.lower():
        #     embed_indices[""] = index
        index += 1
    return embed_indices


async def filter_fields_for_report_embed(embed, embed_indices, enabled):
    new_embed = copy.deepcopy(embed)
    new_embed.clear_fields()
    if embed_indices['gym'] is not None:
        new_embed.add_field(name=embed.fields[embed_indices['gym']].name, value=embed.fields[embed_indices['gym']].value, inline=True) 
    if embed_indices['times'] is not None:
        new_embed.add_field(name=embed.fields[embed_indices['times']].name, value=embed.fields[embed_indices['times']].value, inline=True)
    if embed_indices['team'] is not None:
        new_embed.add_field(name=embed.fields[embed_indices['team']].name, value=embed.fields[embed_indices['team']].value, inline=True)
    if embed_indices['status'] is not None:
        new_embed.add_field(name=embed.fields[embed_indices['status']].name, value=embed.fields[embed_indices['status']].value, inline=True)
    if not enabled:
        if embed_indices['directions'] is not None:
            new_embed.add_field(name=embed.fields[embed_indices['directions']].name, value=embed.fields[embed_indices['directions']].value, inline=True)
    return new_embed


async def build_raid_embeds(kyogre, message, raid_dict, enabled, assume=False):
    guild = message.guild
    author = raid_dict.get('reporter', None)
    if author:
        author = guild.get_member(author)
    utils_cog = kyogre.cogs.get('Utilities')
    location_matching_cog = kyogre.cogs.get('LocationMatching')
    ctype = raid_dict['type']
    raid_embed = discord.Embed(colour=guild.me.colour)
    gym = location_matching_cog.get_gym_by_id(guild.id, raid_dict['gym'])
    if gym:
        gym_info = f"**{gym.name}**\n{'_EX Eligible Gym_' if gym.ex_eligible else ''}"
        if gym.note is not None:
            gym_info += f"\n**Note**: {gym.note}"
        raid_embed.add_field(name='**Gym:**', value=gym_info, inline=False)
        raid_gmaps_link = gym.maps_url
        waze_link = utils_cog.create_waze_query(gym.latitude, gym.longitude)
        apple_link = utils_cog.create_applemaps_query(gym.latitude, gym.longitude)
        raid_embed.add_field(name='**Directions**:',
                             value=f'[Google]({raid_gmaps_link}) | [Waze]({waze_link}) | [Apple]({apple_link})',
                             inline=False)
    if raid_dict['hatch_time']:
        hatch = datetime.datetime.utcfromtimestamp(raid_dict['hatch_time']) + datetime.timedelta(
            hours=kyogre.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        expire = hatch + datetime.timedelta(
            seconds=kyogre.raid_info['raid_eggs'][str(raid_dict['egglevel'])]['raidtime'] * 60)
        exp_msg = f"**Hatches:** {hatch.strftime('%I:%M %p')}\n**Expires:** {expire.strftime('%I:%M %p')}"
    elif raid_dict['expire_time']:
        expire = datetime.datetime.utcfromtimestamp(raid_dict['expire_time']) + datetime.timedelta(
            hours=kyogre.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        hatch = expire + datetime.timedelta(
            seconds=kyogre.raid_info['raid_eggs'][str(raid_dict['egglevel'])]['raidtime'] * 60)
        exp_msg = f"**Hatches:** {hatch.strftime('%I:%M %p')}\n**Expires:**{expire.strftime('%I:%M %p')}"
    else:
        exp_msg = "Set with **!timerset**"
    exp_msg += '\n\n**Next Group**:\nSet with **!starttime**'
    if ctype == 'raid' or assume:
        raid_pokemon = raid_dict['pokemon']
        pkmn = Pokemon.get_pokemon(kyogre, raid_pokemon)
        if enabled:
            min_cp, max_cp = pkmn.get_raid_cp_range(False)
            bmin_cp, bmax_cp = pkmn.get_raid_cp_range(True)
            cp_range = f"**CP Range:** {min_cp}-{max_cp}\n**Boosted:** {bmin_cp}-{bmax_cp}"
            weak_str = utils.types_to_str(guild, pkmn.weak_against.keys(), kyogre.config)
            details = f"**{str(pkmn)}** ({str(pkmn.id)}) {utils.types_to_str(guild, pkmn.types, kyogre.config)}\n" \
                      f"{cp_range}\n**Weak Against**:\n{weak_str}"
            raid_embed.add_field(name='**Details:**', value=details, inline=True)
            raid_embed.add_field(name='**Times:**', value=exp_msg)
        raid_img_url = pkmn.img_url
    else:
        egg_info = kyogre.raid_info['raid_eggs'][str(raid_dict['egglevel'])]
        egg_img = egg_info['egg_img']
        boss_list = []
        for entry in egg_info['pokemon']:
            p = Pokemon.get_pokemon(kyogre, entry)
            boss_list.append(str(p) + utils.types_to_str(guild, p.types, kyogre.config))
        bosslist = '\n'.join(boss_list)
        if len(bosslist) < 1:
            bosslist = kyogre.empty_str
        if enabled:
            raid_embed.add_field(name='**Times:**', value=exp_msg)
            raid_embed.add_field(name='**Possible Bosses:**', value=f'{bosslist}', inline=True)

        raid_img_url = 'https://raw.githubusercontent.com/klords/Kyogre/master/images/eggs/{}?cache=0' \
            .format(str(egg_img))
    if enabled:
        timestamp = (message.created_at + datetime.timedelta(
            hours=kyogre.guild_dict[guild.id]['configure_dict']['settings']['offset'])).strftime(
            '%I:%M %p (%H:%M)')
        if author:
            raid_embed.set_footer(text='Reported by {author} - {timestamp}'
                                  .format(author=author.display_name, timestamp=timestamp),
                                  icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.add_field(name='**Tips:**',
                             value='`!m/!c/!h` for maybe/coming/here\n`!c 2` #s indicate size of party'
                                   '\n`!x` to cancel your status\n`!s` to signal lobby start\n'
                                   '`!shout` to ping raid party\n`!weather` sets the current weather\n',
                             inline=True)
    raid_embed.set_thumbnail(url=raid_img_url)
    report_embed = raid_embed
    embed_indices = await get_embed_field_indices(report_embed)
    report_embed = await filter_fields_for_report_embed(report_embed, embed_indices, enabled)
    return report_embed, raid_embed


def build_invite_embed(bot, guild, trainer_dict):
    description = '**The following trainers would like to be invited to this raid**\n' \
                  f'Those with a {bot.success_react} will be invited by another member.\n\n'
    for trainer in trainer_dict:
        if trainer_dict[trainer].setdefault('invite_status', None) is not None:
            friend_code = bot.guild_dict[guild.id]['trainers'].setdefault('info', {})\
                .setdefault(trainer, {}).get('code', '')
            if trainer_dict[trainer]['invite_status'] == True:
                description += f"{bot.success_react} "
            member = guild.get_member(trainer)
            description += f"**{member.display_name}** {friend_code}\n"
    description += f'\nReact to this message with {server_emoji.get_invite_emoji()} to request an invite.\n' \
                   "Use `!invite trainer` with a trainer mention to indicate you'll invite them.\n\n" \
                   "Use `!set code` to add your Friend Code to your profile and it will appear next to your " \
                   "name in this list."
    return discord.Embed(colour=discord.Colour.from_rgb(232, 128, 183), description=description)

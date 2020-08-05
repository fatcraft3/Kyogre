import asyncio
import copy
import math
import re

from discord.ext import commands

from kyogre import constants, checks, utils

from kyogre.exts.pokemon import Pokemon
from kyogre.exts.locationmatching import Gym

from kyogre.exts.db.kyogredb import LureTypeTable, RewardTable, GuildTable, TrainerTable
from kyogre.exts.db.kyogredb import SubscriptionTable, LocationTable, LocationNoteTable
from kyogre.exts.db.kyogredb import LocationRegionRelation, RegionTable, GymTable
from kyogre.exts.db.kyogredb import Lure, Reward, JOIN, IntegrityError


class Subscriptions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.success_react = '✅'

    subscription_types = {"Raid Boss": "raid",
                          "Gym": "gym",
                          "EX-Eligible": "raid",
                          "Research Reward Pokemon": "research",
                          "Research Reward Items": 'item',
                          "Wild Spawn": "wild",
                          "Pokemon - All types (includes raid, research, and wild)": "pokemon",
                          "Perfect (100 IV spawns)": "wild",
                          "Lures": 'lure'
                          }
    valid_types = ['all', 'pokemon', 'raid', 'research', 'wild', 'nest', 'gym', 'shiny', 'item', 'lure']

    @staticmethod
    def _get_subscription_command_error(content, subscription_types):
        error_message = None

        if ' ' not in content:
            return "Both a subscription type and target must be provided! " \
                   "Type `!help sub (add|remove|list)` for more details!"

        subscription, target = content.split(' ', 1)

        if subscription not in subscription_types:
            error_message = "{subscription} is not a valid subscription type!".format(subscription=subscription.title())

        if target == 'list':
            error_message = "`list` is not a valid target. Did you mean `!sub list`?"
        
        return error_message

    async def _parse_subscription_content(self, content, source, message=None):
        channel = message.channel
        author = message.author
        sub_list = []
        error_list = []
        raid_level_list = [str(n) for n in list(range(1, 6))]
        sub_type, target = content.split(' ', 1)

        if sub_type == 'gym':
            if message:
                channel = message.channel
                guild = message.guild
                gyms = self._get_gyms(guild.id)
                if gyms:
                    gym_dict = {}
                    for t in target.split(','):
                        location_matching_cog = self.bot.cogs.get('LocationMatching')
                        gym = await location_matching_cog.match_prompt(channel, author.id, t, gyms)
                        if gym:
                            if source == 'add':
                                question_spec = 'would you like to be notified'
                            else:
                                question_spec = 'would you like to remove notifications'
                            level = await utils.ask_list(self.bot, f"For {gym.name} which level raids {question_spec}?",
                                                         channel, ['All'] + list(range(1, 6)),
                                                         user_list=[author.id], multiple=True)
                            if level:
                                if 'All' in level:
                                    level = list(range(1, 6))
                                for l in level:
                                    gym_level_dict = gym_dict.get(l, {'ids': [], 'names': []})
                                    gym_level_dict['ids'].append(gym.id)
                                    gym_level_dict['names'].append(gym.name)
                                    gym_dict[l] = gym_level_dict
                            else:
                                error_list.append(t)
                        else:
                            error_list.append(t)
                    for l in gym_dict.keys():
                        entry = f"L{l} Raids at {', '.join(gym_dict[l]['names'])}"
                        sub_list.append(('gym', l, entry, gym_dict[l]['ids']))
                return sub_list, error_list
        if sub_type == 'item':
            result = RewardTable.select(RewardTable.name, RewardTable.quantity)
            result = result.objects(Reward)
            results = [o for o in result]
            item_names = [r.name.lower() for r in results]
            targets = target.split(',')
            for t in targets:
                candidates = utils.get_match(item_names, t, score_cutoff=60, isPartial=True, limit=20)
                name = await utils.prompt_match_result(self.bot, channel, author.id, t, candidates)
                if name is not None:
                    sub_list.append((sub_type, name, name))
                else:
                    error_list.append(t)
            return sub_list, error_list
        if sub_type == 'wild':
            perfect_pattern = r'((100(\s*%)?|perfect)(\s*ivs?\b)?)'
            target, count = re.subn(perfect_pattern, '', target, flags=re.I)
            if count:
                sub_list.append((sub_type, 'perfect', 'Perfect IVs'))

        if sub_type == 'lure':
            result = LureTypeTable.select(LureTypeTable.name)
            result = result.objects(Lure)
            results = [o for o in result]
            lure_names = [r.name.lower() for r in results]
            targets = target.split(',')
            for t in targets:
                candidates = utils.get_match(lure_names, t, score_cutoff=60, isPartial=True, limit=20)
                name = await utils.prompt_match_result(self.bot, channel, author.id, t, candidates)
                if name is not None:
                    sub_list.append((sub_type, name, name))
                else:
                    error_list.append(t)
            return sub_list, error_list
                
        if ',' in target:
            target = set([t.strip() for t in target.split(',')])
        else:
            target = set([target])

        if sub_type == 'raid':
            selected_levels = target.intersection(raid_level_list)
            for level in selected_levels:
                entry = f'L{level} Raids'
                target.remove(level)
                sub_list.append((sub_type, level, entry))

            ex_pattern = r'^(ex([- ]*eligible)?)$'
            ex_r = re.compile(ex_pattern, re.I)
            matches = list(filter(ex_r.match, target))
            if matches:
                entry = 'EX-Eligible Raids'
                for match in matches:
                    target.remove(match)
                sub_list.append((sub_type, 'ex-eligible', entry))
            remaining_list = [str(n) for n in list(range(6, 800))]
            other_numbers = target.intersection(remaining_list)
            for num in other_numbers:
                target.remove(num)
                error_list.append(num)
        
        for name in target:
            pkmn = Pokemon.get_pokemon(self.bot, name)
            if pkmn:
                sub_list.append((sub_type, pkmn.name, pkmn.name))
            else:
                error_list.append(name)
        
        return sub_list, error_list

    @commands.group(name="subscription", aliases=["sub"])
    @checks.allowsubscription()
    async def _sub(self, ctx):
        """Handles user subscriptions"""
        if ctx.invoked_subcommand is None:
            # raise commands.BadArgument()
            await self._guided_subscription(ctx)

    async def _guided_subscription(self, ctx, choice=None):
        message = ctx.message
        channel = message.channel
        author = message.author
        await message.delete()
        choices_list = ['Add', 'Remove', 'View Existing']
        if choice is None:
            prompt = "I'll help you manage your subscriptions!\n\n " \
                     "Would you like to add a new subscription, " \
                     "remove a subscription, or see your current subscriptions?"
            choice = await utils.ask_list(self.bot, prompt, channel, choices_list, user_list=author.id)
        if choice == choices_list[0]:
            prompt = "What type of subscription would you like to add?"
            choices_list = list(self.subscription_types.keys())
            choice = await utils.ask_list(self.bot, prompt, channel, choices_list, user_list=author.id)
            return await self._guided_add(ctx, choice)
        elif choice == choices_list[1]:
            prompt = "What type of subscription would you like to remove?"
            choices_list = ['All'] + list(self.subscription_types.keys())
            choice = await utils.ask_list(self.bot, prompt, channel, choices_list, user_list=author.id)
            return await self._guided_rem(ctx, choice)
        elif choice == choices_list[2]:
            return await ctx.invoke(self.bot.get_command('sub list'))
        else:
            return

    async def _guided_add(self, ctx, sub_type):
        if sub_type == "Raid Boss" or sub_type == "Research Reward Pokemon" \
                or sub_type == "Wild Spawn" or sub_type == "Pokemon - All types (includes raid, research, and wild)":
            prompt = await ctx.channel.send(
                f"Please tell me which Pokemon you'd like to receive **{sub_type}** notifications "
                + "for with a comma between each name")
            result = await self._prompt_selections(ctx, "add")
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            msg_content = self.subscription_types[sub_type] + ' ' + result[0].clean_content
            return await ctx.invoke(self.bot.get_command('sub add'), content=msg_content)
        elif sub_type == "Gym":
            prompt = await ctx.channel.send(
                f"Please tell me which Gyms you'd like to receive raid notifications "
                + "for with a comma between each Gym Name")
            result = await self._prompt_selections(ctx, "add")
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            msg_content = self.subscription_types[sub_type] + ' ' + result[0].clean_content
            return await ctx.invoke(self.bot.get_command('sub add'), content=msg_content)
        elif sub_type == "EX-Eligible":
            return await ctx.invoke(self.bot.get_command('sub add'), content="raid ex")
        elif sub_type == "Perfect (100 IV spawns)":
            return await ctx.invoke(self.bot.get_command('sub add'), content="wild 100")
        elif sub_type == "Research Reward Items":
            prompt = await ctx.channel.send(
                f"Please tell me which **Research Reward Items** you'd like to receive notifications "
                + "for with a comma between each item name.")
            result = await self._prompt_selections(ctx, "add")
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            msg_content = self.subscription_types[sub_type] + ' ' + result[0].clean_content
            return await ctx.invoke(self.bot.get_command('sub add'), content=msg_content)
        elif sub_type == "Lures":
            prompt = await ctx.channel.send(
                f"Please tell me which **Lure Types** you'd like to receive notifications "
                + "for with a comma between each type.\n\n"
                + "Valid types are: Normal, Glacial, Mossy, Magnetic")
            result = await self._prompt_selections(ctx, "add")
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            msg_content = self.subscription_types[sub_type] + ' ' + result[0].clean_content
            return await ctx.invoke(self.bot.get_command('sub add'), content=msg_content)

    async def _guided_rem(self, ctx, type_str):
        message = ctx.message
        channel = message.channel
        sub_type = self.subscription_types[type_str]
        sub_list = self._generate_sub_list_message(ctx, [sub_type])
        if len(sub_list) < 1:
            return await channel.send("You don't have any subscriptions of type **{sub_type}** to remove.")
        if type_str == "All":
            return await ctx.invoke(self.bot.get_command('sub rem'), content="all all")
        if type_str == "EX-Eligible":
            return await ctx.invoke(self.bot.get_command('sub rem'), content="raid ex")
        elif type_str == "Perfect (100 IV spawns)":
            return await ctx.invoke(self.bot.get_command('sub rem'), content="wild 100")
        else:
            prompt = await channel.send(f"Please tell me which {type_str} subscriptions you would "
                                        f"like to remove from the list below, separated by commas. Or reply " +
                                        f"with 'all' to remove all subscriptions of this type.\n\n{sub_list[0]}")
            result = await self._prompt_selections(ctx, "remove")
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            if result[0].clean_content.lower() == 'all':
                msg_content = f" {sub_type} all"
            else:
                msg_content = f" {sub_type} {result[0].clean_content}"
            return await ctx.invoke(self.bot.get_command('sub rem'), content=msg_content)

    async def _prompt_selections(self, ctx, action):
        prompt_msg = None
        try:
            prompt_msg = await self.bot.wait_for('message', timeout=60,
                                                 check=(lambda reply: reply.author == ctx.message.author))
        except asyncio.TimeoutError:
            pass
        if prompt_msg is None:
            return None, f"Failed to {action} subscriptions because you took too long to respond."
        await prompt_msg.delete()
        if prompt_msg.clean_content.lower() == "cancel":
            return None, f"Failed to {action} subscriptions because you cancelled the report."
        return prompt_msg, None

    @_sub.command(name="add")
    async def _sub_add(self, ctx, *, content=None):
        """Create a subscription

        **Usage**: `!sub add <type> <target>`
        Kyogre will send you a notification if an event is generated
        matching the details of your subscription.
        
        **Valid types**: `pokemon, raid, research, wild, gym, item, lure`
        **Note**: 'pokemon' includes raid, research, and wild reports"""
        message = ctx.message
        channel = message.channel
        guild = message.guild
        trainer = message.author.id
        error_list = []

        if content is None:
            return await self._guided_subscription(ctx, 'Add')
        content = content.strip().lower()
        if content == 'shiny':
            candidate_list = [('shiny', 'shiny', 'shiny')]
        else:
            error_message = self._get_subscription_command_error(content, self.valid_types)
            if error_message:
                response = await message.channel.send(error_message)
                return await utils.sleep_and_cleanup([message, response], 10)

            candidate_list, error_list = await self._parse_subscription_content(content, 'add', message)
        
        existing_list = []
        sub_list = []

        # don't remove. this makes sure the guild and trainer are in the db
        guild_obj, __ = GuildTable.get_or_create(snowflake=guild.id)
        trainer_obj, __ = TrainerTable.get_or_create(snowflake=trainer, guild=guild.id)
        if guild_obj is None or trainer_obj is None:
            pass
        s_type = ''
        for sub in candidate_list:
            s_type = sub[0]
            s_target = sub[1]
            s_entry = sub[2]
            if len(sub) > 3:
                spec = sub[3]
                try:
                    result, __ = SubscriptionTable.get_or_create(guild_id=ctx.guild.id, trainer=trainer,
                                                                 type=s_type, target=s_target)
                    current_gym_ids = result.specific
                    split_ids = []
                    if current_gym_ids:
                        current_gym_ids = current_gym_ids.strip('[]')
                        split_id_string = current_gym_ids.split(', ')
                        for s in split_id_string:
                            try:
                                split_ids.append(int(s))
                            except ValueError: 
                                pass
                    spec = [int(s) for s in spec]
                    new_ids = set(split_ids + spec)
                    result.specific = list(new_ids)
                    if len(result.specific) > 0:
                        result.save()
                        sub_list.append(s_entry)
                except:
                    error_list.append(s_entry)
            else:
                try:
                    SubscriptionTable.create(guild_id=ctx.guild.id, trainer=trainer, type=s_type, target=s_target)
                    sub_list.append(s_entry)
                except IntegrityError:
                    existing_list.append(s_entry)
                except:
                    error_list.append(s_entry)

        sub_count = len(sub_list)
        existing_count = len(existing_list)
        error_count = len(error_list)

        confirmation_msg = f'{ctx.author.mention}, successfully added {sub_count} new {s_type} subscriptions'
        if sub_count > 0:
            confirmation_msg += '\n**{sub_count} Added:** \n\t{sub_list}'.format(sub_count=sub_count,
                                                                                 sub_list=',\n\t'.join(sub_list))
        if existing_count > 0:
            confirmation_msg += '\n**{existing_count} Already Existing:** \n\t{existing_list}'\
                .format(existing_count=existing_count, existing_list=', '.join(existing_list))
        if error_count > 0:
            confirmation_msg += '\n**{error_count} Errors:** \n\t{error_list}\n(Check the spelling and try again)'\
                .format(error_count=error_count, error_list=', '.join(error_list))

        await channel.send(content=confirmation_msg)

    @_sub.command(name="remove", aliases=["rm", "rem", "delete", "del"])
    async def _sub_remove(self, ctx, *, content=None):
        """Remove a subscription

        **Usage**: `!sub remove <type> <target>`
        You will no longer be notified of the specified target for the given event type.
        You must remove subscriptions using the same type with which they were added.
        It may be helpful to do `!sub list` first to see your existing subscriptions.

        You can remove all subscriptions of a type:
        `!sub remove <type> all`

        Or remove all subscriptions:
        `!sub remove all all`

        Or started a guided session with:
        `!sub remove`

        **Valid types**: `pokemon, raid, research, wild, gym, item, lure`
        **Note**: 'pokemon' includes raid, research, and wild reports"""
        message = ctx.message
        channel = message.channel
        guild = message.guild
        trainer = message.author.id

        if content is None:
            return await self._guided_subscription(ctx, 'Remove')
        content = content.strip().lower()
        if content == 'shiny':
            sub_type, target = ['shiny', 'shiny']
        else:
            error_message = self._get_subscription_command_error(content, self.valid_types)
            if error_message:
                response = await message.channel.send(error_message)
                return await utils.sleep_and_cleanup([message, response], 10)
            sub_type, target = content.split(' ', 1)

        candidate_list = []
        error_list = []
        not_found_list = []
        remove_list = []

        trainer_query = (TrainerTable
                            .select(TrainerTable.snowflake)
                            .where((TrainerTable.snowflake == trainer) & 
                            (TrainerTable.guild == guild.id)))

        # check for special cases
        skip_parse = False
        
        if sub_type == 'all':
            if target == 'all':
                try:
                    remove_count = SubscriptionTable.delete()\
                        .where((SubscriptionTable.trainer << trainer_query) &
                               (SubscriptionTable.guild_id == ctx.guild.id)).execute()
                    message = f'I removed your {remove_count} subscriptions!'
                except:
                    message = 'I was unable to remove your subscriptions!'
                confirmation_msg = f'{message}'
                await channel.send(content=confirmation_msg)
                return
            else:
                target = target.split(',')
                if sub_type == 'pokemon':
                    for name in target:
                        pkmn = Pokemon.get_pokemon(self.bot, name)
                        if pkmn:
                            candidate_list.append((sub_type, pkmn.name, pkmn.name))
                        else:
                            error_list.append(name)
                if sub_type != "gym":
                    skip_parse = True
        elif target == 'all':
            candidate_list.append((sub_type, target, target))
            skip_parse = True
        elif target == 'shiny':
            candidate_list = [('shiny', 'shiny', 'shiny')]
            sub_type, target = ['shiny', 'shiny']
            skip_parse = True
        if not skip_parse:
            candidate_list, error_list = await self._parse_subscription_content(content, 'remove', message)
        remove_count = 0
        s_type = ''
        for sub in candidate_list:
            s_type = sub[0]
            s_target = sub[1]
            s_entry = sub[2]
            if len(sub) > 3:
                spec = sub[3]
                try:
                    result, __ = SubscriptionTable.get_or_create(guild_id=ctx.guild.id, trainer=trainer,
                                                                 type='gym', target=s_target)
                    current_gym_ids = result.specific
                    split_ids = []
                    if current_gym_ids:
                        current_gym_ids = current_gym_ids.strip('[]')
                        split_id_string = current_gym_ids.split(', ')
                        for s in split_id_string:
                            try:
                                split_ids.append(int(s))
                            except ValueError: 
                                pass
                    for s in spec:
                        if s in split_ids:
                            remove_count += 1
                            split_ids.remove(s)
                    result.specific = split_ids
                    result.save()
                    remove_list.append(s_entry)
                except:
                    error_list.append(s_entry)
            else:
                try:
                    if s_type == 'all':
                        remove_count += SubscriptionTable.delete().where(
                            (SubscriptionTable.trainer << trainer_query) &
                            (SubscriptionTable.target == s_target) &
                            (SubscriptionTable.guild_id == ctx.guild.id)).execute()
                    elif s_target == 'all':
                        remove_count += SubscriptionTable.delete().where(
                            (SubscriptionTable.trainer << trainer_query) &
                            (SubscriptionTable.type == s_type) &
                            (SubscriptionTable.guild_id == ctx.guild.id)).execute()
                    else:
                        remove_count += SubscriptionTable.delete().where(
                            (SubscriptionTable.trainer << trainer_query) &
                            (SubscriptionTable.type == s_type) &
                            (SubscriptionTable.target == s_target) &
                            (SubscriptionTable.guild_id == ctx.guild.id)).execute()
                    if remove_count > 0:
                        remove_list.append(s_entry)
                    else:
                        not_found_list.append(s_entry)
                except:
                    error_list.append(s_entry)

        not_found_count = len(not_found_list)
        error_count = len(error_list)

        confirmation_msg = f'{ctx.author.mention}, successfully removed {remove_count} {s_type} subscriptions'
        if remove_count > 0:
            confirmation_msg += '\n**{remove_count} Removed:** \n\t{remove_list}'\
                .format(remove_count=remove_count, remove_list=',\n\t'.join(remove_list))
        if not_found_count > 0:
            confirmation_msg += '\n**{not_found_count} Not Found:** \n\t{not_found_list}'\
                .format(not_found_count=not_found_count, not_found_list=', '.join(not_found_list))
        if error_count > 0:
            confirmation_msg += '\n**{error_count} Errors:** \n\t{error_list}\n(Check the spelling and try again)'\
                .format(error_count=error_count, error_list=', '.join(error_list))
        await channel.send(content=confirmation_msg)

    @_sub.command(name="list", aliases=["ls"])
    async def _sub_list(self, ctx, *, content=None):
        """Receive a list of all your current subscriptions

        **Usage**: `!sub list [type]`
        
        Include a type to receive a specific list
        **Valid types are**: `pokemon, raid, research, wild, gym, item, lure`

        Or leave type empty to receive complete list of all subscriptions."""
        message = ctx.message
        channel = message.channel
        author = message.author
        response_msg = ''
        invalid_types = []
        valid_types = []
        if content:
            sub_types = [re.sub('[^A-Za-z]+', '', s.lower()) for s in content.split(',')]
            for s in sub_types:
                if s in self.valid_types:
                    valid_types.append(s)
                else:
                    invalid_types.append(s)
            if not valid_types:
                response_msg = "No valid subscription types found! Valid types are: {types}".format(
                    types=', '.join(self.valid_types))
                response = await channel.send(response_msg)
                return await utils.sleep_and_cleanup([message, response], 10)
            if invalid_types:
                response_msg = "\nUnable to find these subscription types: {inv}".format(inv=', '.join(invalid_types))
        listmsg_list = self._generate_sub_list_message(ctx, valid_types)
        response_msg = f"{author.mention}, check your inbox! " \
                       f"I've sent your subscriptions to you directly!" + response_msg
        if len(listmsg_list) > 0:
            if valid_types:
                await author.send(f"Your current {', '.join(valid_types)} subscriptions are:")
                for m in listmsg_list:
                    if len(m) > 0:
                        await author.send(m)
            else:
                await author.send('Your current subscriptions are:')
                for m in listmsg_list:
                    if len(m) > 0:
                        await author.send(m)
        else:
            if valid_types:
                await author.send("You don\'t have any subscriptions for {types}! use the **!subscription add**\
                 command to add some.".format(types=', '.join(valid_types)))
            else:
                await author.send("You don't have any subscriptions!\
                 use the **!subscription add** command to add some.")
        await message.add_reaction(self.success_react)
        return await channel.send(response_msg, delete_after=10)

    @staticmethod
    def _generate_sub_list_message(ctx, types):
        message = ctx.message
        guild = message.guild
        results = (SubscriptionTable
                   .select(SubscriptionTable.type, SubscriptionTable.target, SubscriptionTable.specific)
                   .join(TrainerTable, on=(SubscriptionTable.trainer == TrainerTable.snowflake))
                   .where(SubscriptionTable.trainer == ctx.author.id)
                   .where(TrainerTable.guild == ctx.guild.id)
                   .where(SubscriptionTable.guild_id == ctx.guild.id))
        if len(types) > 0:
            results = results.where(SubscriptionTable.type << types)
        results = results.execute()

        types = set([s.type for s in results])
        for r in results:
            if r.specific:
                current_gym_ids = r.specific.strip('[').strip(']')
                split_id_string = current_gym_ids.split(', ')
                split_ids = []
                for s in split_id_string:
                    try:
                        split_ids.append(int(s))
                    except ValueError:
                        pass

                gyms = (GymTable
                        .select(LocationTable.id,
                                LocationTable.name,
                                LocationTable.latitude,
                                LocationTable.longitude,
                                RegionTable.name.alias('region'),
                                GymTable.ex_eligible,
                                LocationNoteTable.note)
                        .join(LocationTable)
                        .join(LocationRegionRelation)
                        .join(RegionTable)
                        .join(LocationNoteTable, JOIN.LEFT_OUTER,
                              on=(LocationNoteTable.location_id == LocationTable.id))
                        .where((LocationTable.guild == guild.id) &
                               (LocationTable.guild == RegionTable.guild) &
                               (LocationTable.id << split_ids)))
                result = gyms.objects(Gym)
                r.specific = ",\n\t".join([o.name for o in result])
        subscriptions = {}
        for t in types:
            if t == 'gym':
                for r in results:
                    if r.type == 'gym':
                        if r.specific:
                            subscriptions[f"Level {r.target} Raids at"] = r.specific
                        else:
                            msg = subscriptions.get('gym', "")
                            if len(msg) < 1:
                                msg = r.target
                            else:
                                msg += f', {r.target}'
                            subscriptions['gym'] = msg

            else:
                subscriptions[t] = [s.target for s in results if s.type == t and t != 'gym']
        listmsg_list = []
        subscription_msg = ""
        sep = '\n\t'
        for sub in subscriptions.keys():
            if not isinstance(subscriptions[sub], list):
                subscriptions[sub] = [subscriptions[sub]]
            new_msg = f"**Subscription type - {sub.title()}**:\n\t{sep.join(subscriptions[sub])}\n\n"
            if len(subscription_msg) + len(new_msg) < constants.MAX_MESSAGE_LENGTH:
                subscription_msg += new_msg
            else:
                listmsg_list.append(subscription_msg)
                subscription_msg = new_msg
        listmsg_list.append(subscription_msg)
        return listmsg_list

    @_sub.command(name="adminlist", aliases=["alist"])
    @commands.has_permissions(manage_guild=True)
    async def _sub_adminlist(self, ctx, *, trainer=None):
        """**Usage**: `!sub adminlist/alist <member>`
        Receive a list of all current subscriptions the provided member has"""
        message = ctx.message
        channel = message.channel
        author = message.author

        if not trainer:
            response_msg = "Please provide a trainer name or id"
            response = await channel.send(response_msg)
            return await utils.sleep_and_cleanup([message, response], 10)

        if trainer.isdigit():
            trainerid = trainer
        else:
            converter = commands.MemberConverter()
            try:
                trainer_member = await converter.convert(ctx, trainer)
                trainerid = trainer_member.id
            except:
                response_msg = f"Could not process trainer with name: {trainer}"
                await channel.send(response_msg)
                return await utils.sleep_and_cleanup([message, response_msg], 10)
        try:
            results = (SubscriptionTable
                       .select(SubscriptionTable.type, SubscriptionTable.target)
                       .join(TrainerTable, on=(SubscriptionTable.trainer == TrainerTable.snowflake))
                       .where(SubscriptionTable.trainer == trainerid)
                       .where(TrainerTable.guild == ctx.guild.id)
                       .where(SubscriptionTable.guild_id == ctx.guild.id))

            results = results.execute()
            subscription_msg = ''
            types = set([s.type for s in results])
            subscriptions = {t: [s.target for s in results if s.type == t] for t in types}

            for sub in subscriptions:
                subscription_msg += '**{category}**:\n\t{subs}\n\n'.format(category=sub.title(),
                                                                           subs='\n\t'.join(subscriptions[sub]))
            if len(subscription_msg) > 0:
                listmsg = "Listing subscriptions for user:  {id}\n".format(id=trainer)
                listmsg += 'Current subscriptions are:\n\n{subscriptions}'.format(subscriptions=subscription_msg)
                await message.add_reaction(self.success_react)
                await author.send(listmsg)
            else:
                none_msg = await channel.send(f"No subscriptions found for user: {trainer}")
                await message.add_reaction(self.success_react)
                return await utils.sleep_and_cleanup([none_msg], 10)
        except:
            response_msg = f"Encountered an error while looking up subscriptions for trainer with name: {trainer}"
            await channel.send(response_msg)
            return await utils.sleep_and_cleanup([response_msg, message], 10)

    def _get_gyms(self, guild_id, regions=None):
        location_matching_cog = self.bot.cogs.get('LocationMatching')
        if not location_matching_cog:
            return None
        gyms = location_matching_cog.get_gyms(guild_id, regions)
        return gyms

    @staticmethod
    def close_enough(coord1, coord2, distance):
        #haversine
        R = 6372800  # Earth radius in meters
        conv = 1609.34 # meters in a mile
        lat1, lon1 = coord1
        lat2, lon2 = coord2
        
        phi1, phi2 = math.radians(lat1), math.radians(lat2) 
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = math.sin(dphi/2)**2 + \
            math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        
        return 2*R*math.atan2(math.sqrt(a), math.sqrt(1 - a)) / conv < distance

    async def send_notifications_async(self, notification_type, details, new_channel, exclusions=[]):
        valid_types = ['raid', 'research', 'wild', 'nest', 'gym', 'shiny', 'item', 'lure', 'hideout']
        if notification_type not in valid_types:
            return
        guild = new_channel.guild
        # get trainers
        try:
            results = (SubscriptionTable
                       .select(SubscriptionTable.trainer, SubscriptionTable.target, SubscriptionTable.specific)
                       .join(TrainerTable, on=(SubscriptionTable.trainer == TrainerTable.snowflake))
                       .where((SubscriptionTable.type == notification_type) |
                              (SubscriptionTable.type == 'pokemon') |
                              (SubscriptionTable.type == 'gym'))
                       .where(TrainerTable.guild == guild.id)
                       .where(SubscriptionTable.guild_id == guild.id)).execute()
        except:
            return
        # group targets by trainer
        trainers = set([s.trainer for s in results])
        target_dict = {t: {s.target: s.specific for s in results if s.trainer == t} for t in trainers}
        regions = set(details.get('regions', []))
        ex_eligible = details.get('ex-eligible', None)
        tier = details.get('tier', None)
        perfect = details.get('perfect', None)
        pokemon_list = details.get('pokemon', [])
        gym = details.get('location', None)
        item = details.get('item', None)
        lure_type = details.get('lure_type', None)
        if not isinstance(pokemon_list, list):
            pokemon_list = [pokemon_list]
        location = details.get('location', None)
        multi = details.get('multi', False)
        region_dict = self.bot.guild_dict[guild.id]['configure_dict'].get('regions', None)
        outbound_dict = {}
        # build final dict
        for trainer in target_dict:
            user = guild.get_member(trainer)
            if trainer in exclusions or not user:
                continue
            if region_dict and region_dict.get('enabled', False):
                matched_regions = [n for n, o in region_dict.get('info', {}).items() if
                                   o['role'] in [r.name for r in user.roles]]
                if regions and regions.isdisjoint(matched_regions):
                    continue
            targets = target_dict[trainer]
            descriptors = []
            target_matched = False
            if 'ex-eligible' in targets and ex_eligible:
                target_matched = True
                descriptors.append('ex-eligible')
            if tier and str(tier) in targets:
                tier = str(tier)
                if targets[tier]:
                    try:
                        current_gym_ids = targets[tier].strip('[').strip(']')
                        split_id_string = current_gym_ids.split(', ')
                        split_ids = []
                        for s in split_id_string:
                            try:
                                split_ids.append(int(s))
                            except ValueError:
                                pass
                        target_gyms = (GymTable
                                       .select(LocationTable.id,
                                               LocationTable.name,
                                               LocationTable.latitude,
                                               LocationTable.longitude,
                                               RegionTable.name.alias('region'),
                                               GymTable.ex_eligible,
                                               LocationNoteTable.note)
                                       .join(LocationTable)
                                       .join(LocationRegionRelation)
                                       .join(RegionTable)
                                       .join(LocationNoteTable, JOIN.LEFT_OUTER,
                                             on=(LocationNoteTable.location_id == LocationTable.id))
                                       .where((LocationTable.guild == guild.id) &
                                              (LocationTable.guild == RegionTable.guild) &
                                              (LocationTable.id << split_ids)))
                        target_gyms = target_gyms.objects(Gym)
                        found_gym_names = [r.name for r in target_gyms]
                        if gym in found_gym_names:
                            target_matched = True
                    except:
                        pass
                else:
                    target_matched = True
                descriptors.append('level {level}'.format(level=details['tier']))
            pkmn_adj = ''
            if perfect and 'perfect' in targets:
                target_matched = True
                pkmn_adj = 'perfect '
            for pokemon in pokemon_list:
                if pokemon.name in targets:
                    target_matched = True
                full_name = pkmn_adj + pokemon.name
                descriptors.append(full_name)
            if gym in targets:
                target_matched = True
            if item and item.lower() in targets:
                target_matched = True
            if 'shiny' in targets:
                target_matched = True
            if 'takeover' in targets or (lure_type and lure_type in targets):
                trainer_info = self.bot.guild_dict[guild.id]['trainers'].setdefault('info', {}).setdefault(trainer, {})
                t_location = trainer_info.setdefault('location', None)
                distance = trainer_info.setdefault('distance', None)
                stop = details['location']
                if t_location is not None and distance is not None:
                    if self.close_enough((float(stop.latitude), float(stop.longitude)),
                                         (t_location[0], t_location[1]), distance):
                        target_matched = True
                    else:
                        target_matched = False
                else:
                    target_matched = True
            if not target_matched:
                continue
            description = ', '.join(descriptors)
            start = 'An' if re.match(r'^[aeiou]', description, re.I) else 'A'
            if notification_type == 'item':
                start = 'An' if re.match(r'^[aeiou]', item, re.I) else 'A'
                if multi:
                    location = 'multiple locations'
                message = f'{start} **{item} research task** has been reported at **{location}**!'
            elif notification_type == 'lure':
                message = f'A **{lure_type.capitalize()}** lure has been dropped at {location.name}!'
            elif notification_type == 'hideout':
                message = f'A **Team Rocket Hideout** has been spotted at {location.name}!'
            elif notification_type == 'wild':
                message = f'A **wild {description} spawn** has been reported at **{location}**!'
            elif notification_type == 'research':
                if multi:
                    location = 'multiple locations'
                message = f'{start} **{description} research task** has been reported at **{location}**!'
            elif 'hatching' in details and details['hatching']:
                message = f"The egg at **{location}** has hatched into {start.lower()} **{description}** raid!"
            else:
                message = f'{start} {description} {notification_type} at {location} has been reported!'
            outbound_dict[trainer] = {'discord_obj': user, 'message': message}
        pokemon_names = ' '.join([p.name for p in pokemon_list])
        if notification_type == 'item':
            role_name = utils.sanitize_name(f"{item} {location}".title())
        elif notification_type == 'lure':
            role_name = utils.sanitize_name(f'{lure_type} {location.name}'.title())
        elif notification_type == 'hideout':
            role_name = utils.sanitize_name(f'Rocket Hideout {location.name}'.title())
        else:
            role_name = utils.sanitize_name(f"{notification_type} {pokemon_names} {location}".title())
        # starting to hit rate limit for role creation so explicitly mentioning all trainers in the meantime
        await self.notify_all_async(new_channel, outbound_dict)
        faves_cog = self.bot.cogs.get('Faves')
        return faves_cog.get_report_points(guild, pokemon_list, notification_type, perfect)
        #return await self.generate_role_notification_async(role_name, new_channel, outbound_dict)

    @staticmethod
    async def notify_all_async(channel, outbound_dict):
        if len(outbound_dict) == 0:
            return
        guild = channel.guild
        trainer_notify_string = ''
        for trainer in outbound_dict.values():
            try:
                user = guild.get_member(trainer['discord_obj'].id)
                trainer_notify_string += user.mention
            except:
                pass
        # send notification message in channel
        obj = next(iter(outbound_dict.values()))
        message = obj['message']
        msg_obj = await channel.send(f'{message} {trainer_notify_string}')

        async def cleanup():
            await asyncio.sleep(60)
            try:
                await msg_obj.delete()
            except:
                pass

        asyncio.ensure_future(cleanup())

    @staticmethod
    async def generate_role_notification_async(role_name, channel, outbound_dict):
        """Generates and handles a temporary role notification in the new raid channel"""
        if len(outbound_dict) == 0:
            return
        guild = channel.guild
        # generate new role
        temp_role = await guild.create_role(name=role_name, hoist=False, mentionable=True)
        for trainer in outbound_dict.values():
            await trainer['discord_obj'].add_roles(temp_role)
        # send notification message in channel
        obj = next(iter(outbound_dict.values()))
        message = obj['message']
        msg_obj = await channel.send(f'{temp_role.mention} {message}')

        async def cleanup():
            await asyncio.sleep(60)
            await temp_role.delete()
            try:
                await msg_obj.delete()
            except:
                pass
        asyncio.ensure_future(cleanup())

    def get_region_list_channel(self, guild, region, event_type):
        send_channel = None
        listing_dict = self.bot.guild_dict[guild.id]['configure_dict'].get(event_type, {}).get('listings', None)
        if listing_dict and listing_dict['enabled']:
            if 'channel' in listing_dict:
                send_channel = self.bot.get_channel(listing_dict['channel']['id'])
            if 'channels' in listing_dict:
                channel_map = listing_dict['channels'].get(region, None)
                if channel_map:
                    send_channel = self.bot.get_channel(channel_map['id'])
        return send_channel


def setup(bot):
    bot.add_cog(Subscriptions(bot))

import asyncio
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

    subscription_types = {"Raid Boss": "raid",
                          "Raid Tier": "raid",
                          "Gym": "gym",
                          "EX-Eligible": "raid",
                          "Research Reward": "research",
                          "Wild Spawn": "wild",
                          "Pokemon - All types (includes raid, research, and wild)": "pokemon",
                          "Perfect (100 IV spawns)": "wild"
                          }

    def _get_subscription_command_error(self, content, subscription_types):
        error_message = None

        if ' ' not in content:
            return "Both a subscription type and target must be provided! Type `!help sub (add|remove|list)` for more details!"

        subscription, target = content.split(' ', 1)

        if subscription not in subscription_types:
            error_message = "{subscription} is not a valid subscription type!".format(subscription=subscription.title())

        if target == 'list':
            error_message = "`list` is not a valid target. Did you mean `!sub list`?"
        
        return error_message

    async def _parse_subscription_content(self, content, source, message = None):
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
                trainer = message.author.id
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
            result = RewardTable.select(RewardTable.name,RewardTable.quantity)
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
            ex_pattern = r'^(ex([- ]*eligible)?)$'
            ex_r = re.compile(ex_pattern, re.I)
            matches = list(filter(ex_r.match, target))
            if matches:
                entry = 'EX-Eligible Raids'
                for match in matches:
                    target.remove(match)
                sub_list.append((sub_type, 'ex-eligible', entry))
        
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

    async def _guided_subscription(self, ctx):
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        await message.delete()
        prompt = "I'll help you manage your subscriptions!\n\n" \
        + "Would you like to add a new subscription, remove a subscription, or see your current subscriptions?"
        choices_list = ['Add', 'Remove', 'View Existing']

        match = await utils.ask_list(self.bot, prompt, channel, choices_list, user_list=author.id)
        if match == choices_list[0]:
            prompt = "What type of subscription would you like to add?"
            choices_list = list(self.subscription_types.keys())
            match = await utils.ask_list(self.bot, prompt, channel, choices_list, user_list=author.id)
            return await self._guided_add(ctx, match)
        elif match == choices_list[1]:
            pass
        elif match == choices_list[2]:
            pass
        else:
            return

    async def _guided_add(self, ctx, type):
        if type == "Raid Boss" or type == "Research Reward" \
                or type == "Wild Spawn" or type == "Pokemon - All types (includes raid, research, and wild)":
            prompt = await ctx.channel.send(
                f"Please tell me which Pokemon you'd like to receive **{type}** notifications "
                + "for with a comma between each name")
            result = await self._prompt_selections(ctx)
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            msg_content = self.subscription_types[type] + ' ' + result[0].clean_content
            return await ctx.invoke(self.bot.get_command('sub add'), content=msg_content)
        elif type == "Raid Tier":
            prompt = await ctx.channel.send(
                f"Please tell me which **Raid Tiers** you'd like to receive notifications "
                + "for with a comma between each number")
            result = await self._prompt_selections(ctx)
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            msg_content = self.subscription_types[type] + ' ' + result[0].clean_content
            return await ctx.invoke(self.bot.get_command('sub add'), content=msg_content)
        elif type == "Gym":
            prompt = await ctx.channel.send(
                f"Please tell me which Gyms you'd like to receive raid notifications "
                + "for with a comma between each Gym Name")
            result = await self._prompt_selections(ctx)
            await prompt.delete()
            if result[0] is None:
                return await ctx.send(result[1])
            msg_content = self.subscription_types[type] + ' ' + result[0].clean_content
            return await ctx.invoke(self.bot.get_command('sub add'), content=msg_content)
        elif type == "EX-Eligible":
            return await ctx.invoke(self.bot.get_command('sub add'), content="raid ex")
        elif type == "Perfect (100 IV spawns)":
            return await ctx.invoke(self.bot.get_command('sub add'), content="wild 100")

    async def _prompt_selections(self, ctx):
        try:
            prompt_msg = await self.bot.wait_for('message', timeout=60,
                                                 check=(lambda reply: reply.author == ctx.message.author))
        except asyncio.TimeoutError:
            pass
        error = None
        await prompt_msg.delete()
        if not prompt_msg:
            error = "you took too long to respond"
        elif prompt_msg.clean_content.lower() == "cancel":
            error = "you cancelled the report"
        if error:
            return None, f"Failed to add subscriptions because {error}"
        return prompt_msg, None

    @_sub.command(name="add")
    async def _sub_add(self, ctx, *, content):
        """Create a subscription

        Usage: !sub add <type> <target>
        Kyogre will send you a notification if an event is generated
        matching the details of your subscription.
        
        Valid types are: pokemon, raid, research, wild, and gym
        Note: 'Pokemon' includes raid, research, and wild reports"""
        subscription_types = ['pokemon','raid','research','wild','nest','gym','shiny','item','lure']
        message = ctx.message
        channel = message.channel
        guild = message.guild
        trainer = message.author.id
        error_list = []

        content = content.strip().lower()
        if content == 'shiny':
            candidate_list = [('shiny', 'shiny', 'shiny')]
        else:
            error_message = self._get_subscription_command_error(content, subscription_types)
            if error_message:
                response = await message.channel.send(error_message)
                return await utils.sleep_and_cleanup([message, response], 10)

            candidate_list, error_list = await self._parse_subscription_content(content, 'add', message)
        
        existing_list = []
        sub_list = []

        # don't remove. this makes sure the guild and trainer are in the db
        guild_obj, __ = GuildTable.get_or_create(snowflake=guild.id)
        trainer_obj, __ = TrainerTable.get_or_create(snowflake=trainer, guild=guild.id)

        for sub in candidate_list:
            s_type = sub[0]
            s_target = sub[1]
            s_entry = sub[2]
            if len(sub) > 3:
                spec = sub[3]
                try:
                    result, __ = SubscriptionTable.get_or_create(trainer=trainer, type=s_type, target=s_target)
                    current_gym_ids = result.specific
                    split_ids = []
                    if current_gym_ids:
                        current_gym_ids = current_gym_ids.strip('[').strip(']')
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
                    SubscriptionTable.create(trainer=trainer, type=s_type, target=s_target)
                    sub_list.append(s_entry)
                except IntegrityError:
                    existing_list.append(s_entry)
                except:
                    error_list.append(s_entry)

        sub_count = len(sub_list)
        existing_count = len(existing_list)
        error_count = len(error_list)

        confirmation_msg = '{member}, successfully added {count} new subscriptions'.format(member=ctx.author.mention, count=sub_count)
        if sub_count > 0:
            confirmation_msg += '\n**{sub_count} Added:** \n\t{sub_list}'.format(sub_count=sub_count, sub_list=',\n\t'.join(sub_list))
        if existing_count > 0:
            confirmation_msg += '\n**{existing_count} Already Existing:** \n\t{existing_list}'.format(existing_count=existing_count, existing_list=', '.join(existing_list))
        if error_count > 0:
            confirmation_msg += '\n**{error_count} Errors:** \n\t{error_list}\n(Check the spelling and try again)'.format(error_count=error_count, error_list=', '.join(error_list))

        await channel.send(content=confirmation_msg)

    @_sub.command(name="remove", aliases=["rm", "rem"])
    async def _sub_remove(self, ctx,*,content):
        """Remove a subscription

        Usage: !sub remove <type> <target>
        You will no longer be notified of the specified target for the given event type.

        You can remove all subscriptions of a type:
        !sub remove <type> all

        Or remove all subscriptions:
        !sub remove all all"""
        subscription_types = ['all','pokemon','raid','research','wild','nest','gym','shiny','item','lure']
        message = ctx.message
        channel = message.channel
        guild = message.guild
        trainer = message.author.id

        content = content.strip().lower()
        if content == 'shiny':
            sub_type, target = ['shiny','shiny']
        else:
            error_message = self._get_subscription_command_error(content, subscription_types)
            if error_message:
                response = await message.channel.send(error_message)
                return await utils.sleep_and_cleanup([message,response], 10)
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
                    remove_count = SubscriptionTable.delete().where((SubscriptionTable.trainer << trainer_query)).execute()
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
            sub_type, target = ['shiny','shiny']
            skip_parse = True
        if not skip_parse:
            candidate_list, error_list = await self._parse_subscription_content(content, 'remove', message)
        remove_count = 0
        for sub in candidate_list:
            s_type = sub[0]
            s_target = sub[1]
            s_entry = sub[2]
            if len(sub) > 3:
                spec = sub[3]
                try:
                    result, __ = SubscriptionTable.get_or_create(trainer=trainer, type='gym', target=s_target)
                    current_gym_ids = result.specific
                    split_ids = []
                    if current_gym_ids:
                        current_gym_ids = current_gym_ids.strip('[').strip(']')
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
                            (SubscriptionTable.target == s_target)).execute()
                    elif s_target == 'all':
                        remove_count += SubscriptionTable.delete().where(
                            (SubscriptionTable.trainer << trainer_query) &
                            (SubscriptionTable.type == s_type)).execute()
                    else:
                        remove_count += SubscriptionTable.delete().where(
                            (SubscriptionTable.trainer << trainer_query) &
                            (SubscriptionTable.type == s_type) &
                            (SubscriptionTable.target == s_target)).execute()
                    if remove_count > 0:
                        remove_list.append(s_entry)
                    else:
                        not_found_list.append(s_entry)
                except:
                    error_list.append(s_entry)

        not_found_count = len(not_found_list)
        error_count = len(error_list)

        confirmation_msg = '{member}, successfully removed {count} subscriptions'\
            .format(member=ctx.author.mention, count=remove_count)
        if remove_count > 0:
            confirmation_msg += '\n**{remove_count} Removed:** \n\t{remove_list}'\
                .format(remove_count=remove_count, remove_list=',\n'.join(remove_list))
        if not_found_count > 0:
            confirmation_msg += '\n**{not_found_count} Not Found:** \n\t{not_found_list}'\
                .format(not_found_count=not_found_count, not_found_list=', '.join(not_found_list))
        if error_count > 0:
            confirmation_msg += '\n**{error_count} Errors:** \n\t{error_list}\n(Check the spelling and try again)'\
                .format(error_count=error_count, error_list=', '.join(error_list))
        await channel.send(content=confirmation_msg)


    @_sub.command(name="list", aliases=["ls"])
    async def _sub_list(self, ctx, *, content=None):
        """List the subscriptions for the user

        Usage: !sub list <type> 
        Leave type empty to receive complete list of all subscriptions.
        Or include a type to receive a specific list
        Valid types are: pokemon, raid, research, wild, and gym"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        subscription_types = ['pokemon','raid','research','wild','nest','gym','item']
        response_msg = ''
        invalid_types = []
        valid_types = []
        results = (SubscriptionTable
                    .select(SubscriptionTable.type, SubscriptionTable.target, SubscriptionTable.specific)
                    .join(TrainerTable, on=(SubscriptionTable.trainer == TrainerTable.snowflake))
                    .where(SubscriptionTable.trainer == ctx.author.id)
                    .where(TrainerTable.guild == ctx.guild.id))

        if content:
            sub_types = [re.sub('[^A-Za-z]+', '', s.lower()) for s in content.split(',')]
            for s in sub_types:
                if s in subscription_types:
                    valid_types.append(s)
                else:
                    invalid_types.append(s)

            if valid_types:
                results = results.where(SubscriptionTable.type << valid_types)
            else:
                response_msg = "No valid subscription types found! Valid types are: {types}".format(types=', '.join(subscription_types))
                response = await channel.send(response_msg)
                return await utils.sleep_and_cleanup([message,response], 10)
            
            if invalid_types:
                response_msg = "\nUnable to find these subscription types: {inv}".format(inv=', '.join(invalid_types))
        
        results = results.execute()
            
        response_msg = f"{author.mention}, check your inbox! I've sent your subscriptions to you directly!" + response_msg
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
                        .join(LocationNoteTable, JOIN.LEFT_OUTER, on=(LocationNoteTable.location_id == LocationTable.id))
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
        for sub in subscriptions.keys():
            if not isinstance(subscriptions[sub], list):
                subscriptions[sub] = [subscriptions[sub]]
            new_msg = '**{category}**:\n\t{subs}\n\n'.format(category=sub.title(),subs='\n\t'.join(subscriptions[sub]))
            if len(subscription_msg) + len(new_msg) < constants.MAX_MESSAGE_LENGTH:
                subscription_msg += new_msg
            else:
                listmsg_list.append(subscription_msg)
                subscription_msg = new_msg
        listmsg_list.append(subscription_msg)
        if len(listmsg_list) > 0:
            if valid_types:
                await author.send(f"Your current {', '.join(valid_types)} subscriptions are:")
                for message in listmsg_list:
                    await author.send(message)
            else:
                await author.send('Your current subscriptions are:')
                for message in listmsg_list:
                    await author.send(message)
        else:
            if valid_types:
                await author.send("You don\'t have any subscriptions for {types}! use the **!subscription add** command to add some.".format(types=', '.join(valid_types)))
            else:
                await author.send("You don\'t have any subscriptions! use the **!subscription add** command to add some.")
        response = await channel.send(response_msg)
        await utils.sleep_and_cleanup([message,response], 10)


    @_sub.command(name="adminlist", aliases=["alist"])
    @commands.has_permissions(manage_guild=True)
    async def _sub_adminlist(self, ctx, *, trainer=None):
        message = ctx.message
        channel = message.channel
        author = message.author

        if not trainer:
            response_msg = "Please provide a trainer name or id"
            response = await channel.send(response_msg)
            return await utils.sleep_and_cleanup([message,response], 10)

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
                return await utils.sleep_and_cleanup([message,response_msg], 10)
        try:
            results = (SubscriptionTable
                .select(SubscriptionTable.type, SubscriptionTable.target)
                .join(TrainerTable, on=(SubscriptionTable.trainer == TrainerTable.snowflake))
                .where(SubscriptionTable.trainer == trainerid)
                .where(TrainerTable.guild == ctx.guild.id))

            results = results.execute()
            subscription_msg = ''
            types = set([s.type for s in results])
            subscriptions = {t: [s.target for s in results if s.type == t] for t in types}

            for sub in subscriptions:
                subscription_msg += '**{category}**:\n\t{subs}\n\n'.format(category=sub.title(),subs='\n\t'.join(subscriptions[sub]))
            if len(subscription_msg) > 0:
                listmsg = "Listing subscriptions for user:  {id}\n".format(id=trainer)
                listmsg += 'Current subscriptions are:\n\n{subscriptions}'.format(subscriptions=subscription_msg)
                await message.add_reaction('✅')
                await author.send(listmsg)
            else:
                none_msg = await channel.send(f"No subscriptions found for user: {trainer}")
                await message.add_reaction('✅')
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

    async def generate_role_notification_async(self, role_name, channel, outbound_dict):
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
            await asyncio.sleep(300)
            await temp_role.delete()
            await msg_obj.delete()
        asyncio.ensure_future(cleanup())

def setup(bot):
    bot.add_cog(Subscriptions(bot))
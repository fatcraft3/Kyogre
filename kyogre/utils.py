import asyncio
import datetime
import dateparser
import re

from dateutil.relativedelta import relativedelta
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

import discord
from kyogre import checks


def get_match(word_list: list, word: str, score_cutoff: int = 60, isPartial: bool = False, limit: int = 1):
    """Uses fuzzywuzzy to see if word is close to entries in word_list

    Returns a tuple of (MATCH, SCORE)
    """
    if not word:
        return (None, None)
    result = None
    scorer = fuzz.ratio
    if isPartial:
        scorer = fuzz.partial_ratio
    if limit == 1:
        result = process.extractOne(word, word_list,
                                    scorer=scorer, score_cutoff=score_cutoff)
    else:
        result = process.extractBests(word, word_list,
                                      scorer=scorer, score_cutoff=score_cutoff, limit=limit)
    if not result:
        return (None, None)
    return result


def colour(*args):
    """Returns a discord Colour object.

    Pass one as an argument to define colour:
        `int` match colour value.
        `str` match common colour names.
        `discord.Guild` bot's guild colour.
        `None` light grey.
    """
    arg = args[0] if args else None
    if isinstance(arg, int):
        return discord.Colour(arg)
    if isinstance(arg, str):
        colour = arg
        try:
            return getattr(discord.Colour, colour)()
        except AttributeError:
            return discord.Colour.lighter_grey()
    if isinstance(arg, discord.Guild):
        return arg.me.colour
    else:
        return discord.Colour.lighter_grey()


def make_embed(msg_type='', title=None, icon=None, content=None,
               msg_colour=None, guild=None, title_url=None,
               thumbnail='', image='', fields=None, footer=None,
               footer_icon=None, inline=False):
    """Returns a formatted discord embed object.

    Define either a type or a colour.
    Types are:
    error, warning, info, success, help.
    """

    embed_types = {
        'error': {
            'icon': 'https://i.imgur.com/juhq2uJ.png',
            'colour': 'red'
        },
        'warning': {
            'icon': 'https://i.imgur.com/4JuaNt9.png',
            'colour': 'gold'
        },
        'info': {
            'icon': 'https://i.imgur.com/wzryVaS.png',
            'colour': 'blue'
        },
        'success': {
            'icon': 'https://i.imgur.com/ZTKc3mr.png',
            'colour': 'green'
        },
        'help': {
            'icon': 'https://i.imgur.com/kTTIZzR.png',
            'colour': 'blue'
        }
    }
    if msg_type in embed_types.keys():
        msg_colour = embed_types[msg_type]['colour']
        icon = embed_types[msg_type]['icon']
    if guild and not msg_colour:
        msg_colour = colour(guild)
    else:
        if not isinstance(msg_colour, discord.Colour):
            msg_colour = colour(msg_colour)
    embed = discord.Embed(description=content, colour=msg_colour)
    if not title_url:
        title_url = discord.Embed.Empty
    if not icon:
        icon = discord.Embed.Empty
    if title:
        embed.set_author(name=title, icon_url=icon, url=title_url)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if fields:
        for key, value in fields.items():
            ilf = inline
            if not isinstance(value, str):
                ilf = value[0]
                value = value[1]
            embed.add_field(name=key, value=value, inline=ilf)
    if footer:
        footer = {'text': footer}
        if footer_icon:
            footer['icon_url'] = footer_icon
        embed.set_footer(**footer)
    return embed


def bold(msg: str):
    """Format to bold markdown text"""
    return f'**{msg}**'


def italics(msg: str):
    """Format to italics markdown text"""
    return f'*{msg}*'


def bolditalics(msg: str):
    """Format to bold italics markdown text"""
    return f'***{msg}***'


def code(msg: str):
    """Format to markdown code block"""
    return f'```{msg}```'


def pycode(msg: str):
    """Format to code block with python code highlighting"""
    return f'```py\n{msg}```'


def ilcode(msg: str):
    """Format to inline markdown code"""
    return f'`{msg}`'


def convert_to_bool(argument):
    lowered = argument.lower()
    if lowered in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
        return True
    elif lowered in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
        return False
    else:
        return None


def sanitize_channel_name(name):
    """Converts a given string into a compatible discord channel name."""
    # Remove all characters other than alphanumerics,
    # dashes, underscores, and spaces
    ret = re.sub('[^a-zA-Z0-9 _\\-]', '', name)
    # Replace spaces with dashes
    ret = ret.replace(' ', '-')
    return ret


async def get_raid_help(prefix, avatar, user=None):
    helpembed = discord.Embed(colour=discord.Colour.lighter_grey())
    helpembed.set_author(name="Raid Coordination Help", icon_url=avatar)
    helpembed.add_field(
        name="Key",
        value="<> denote required arguments, [] denote optional arguments",
        inline=False)
    helpembed.add_field(
        name="Raid MGMT Commands",
        value=(
            f"`{prefix}raid <species>`\n"
            f"`{prefix}weather <weather>`\n"
            f"`{prefix}timerset <minutes>`\n"
            f"`{prefix}starttime <time>`\n"
            "`<google maps link>`\n"
            "**RSVP**\n"
            f"`{prefix}(i/c/h)...\n"
            "[total]...\n"
            "[team counts]`\n"
            "**Lists**\n"
            f"`{prefix}list [status]`\n"
            f"`{prefix}list [status] tags`\n"
            f"`{prefix}list teams`\n\n"
            f"`{prefix}starting [team]`"))
    helpembed.add_field(
        name="Description",
        value=(
            "`Hatches Egg channel`\n"
            "`Sets in-game weather`\n"
            "`Sets hatch/raid timer`\n"
            "`Sets start time`\n"
            "`Updates raid location`\n\n"
            "`interested/coming/here`\n"
            "`# of trainers`\n"
            "`# from each team (ex. 3m for 3 Mystic)`\n\n"
            "`Lists trainers by status`\n"
            "`@mentions trainers by status`\n"
            "`Lists trainers by team`\n\n"
            "`Moves trainers on 'here' list to a lobby.`"))
    if not user:
        return helpembed
    await user.send(embed=helpembed)


def get_level(bot, pkmn):
    for level, pkmn_list in bot.raid_info['raid_eggs'].items():
        if pkmn.lower() in pkmn_list["pokemon"]:
            return level


def get_effectiveness(type_eff):
    if type_eff == 1:
        return 1.4
    if type_eff == -1:
        return 0.714
    if type_eff == -2:
        return 0.51
    return 1


async def simple_ask(Kyogre, message, destination, user_list=None, *, react_list=['✅', '❌']):
    if user_list and not isinstance(user_list, list):
        user_list = [user_list]

    def check(reaction, user):
        if user_list and isinstance(user_list, list):
            return (user.id in user_list) and (reaction.message.id == message.id) and (reaction.emoji in react_list)
        elif not user_list:
            return (user.id != message.guild.me.id) and (reaction.message.id == message.id) and (
                        reaction.emoji in react_list)

    for r in react_list:
        await asyncio.sleep(0.25)
        try:
            await message.add_reaction(r)
        except:
            print(f"couldn't add reaction {r}")
    try:
        reaction, user = await Kyogre.wait_for('reaction_add', check=check, timeout=60)
        return reaction, user
    except asyncio.TimeoutError:
        await message.clear_reactions()
        return


async def ask(bot, message, user_list=None, timeout=60, *, react_list=['✅', '❌'], multiple=False):
    finish_multiple = '👍'
    if user_list and not isinstance(user_list, list):
        user_list = [user_list]

    def check(reaction, user):
        if user_list and isinstance(user_list, list):
            return (user.id in user_list) and (reaction.message.id == message.id) and (reaction.emoji in react_list)
        elif not user_list:
            return (user.id != message.author.id) and (reaction.message.id == message.id) and (
                        reaction.emoji in react_list)

    for r in react_list:
        await asyncio.sleep(0.25)
        await message.add_reaction(r)
    try:
        reactions = []
        while True:
            done, pending = await asyncio.wait([
                bot.wait_for('reaction_add', check=check),
                bot.wait_for('reaction_remove', check=check)
            ], timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED)
            for future in pending:
                future.cancel()
            try:
                stuff = done.pop().result()
                reaction = stuff[0]
                user = stuff[1]
                if reaction in reactions:
                    reactions.remove(reaction)
                else:
                    if multiple:
                        if reaction.emoji != finish_multiple:
                            reactions.append(reaction)
                        else:
                            return reactions, user
                    else:
                        return reaction, user
            except:
                pass

    except asyncio.TimeoutError:
        await message.delete()
        return


async def ask_list(bot, prompt, destination, choices_list, options_emoji_list=None, user_list=None, *, allow_edit=False,
                   multiple=False):
    if not choices_list:
        return None
    if not options_emoji_list:
        options_emoji_list = [str(i) + '\u20e3' for i in range(10)]
    if not isinstance(user_list, list):
        user_list = [user_list]
    next_emoji = '➡'
    next_emoji_text = '➡️'
    edit_emoji = '✏'
    edit_emoji_text = '✏️'
    cancel_emoji = '❌'
    finish_multiple = '👍'
    num_pages = (len(choices_list) - 1) // len(options_emoji_list)
    for offset in range(num_pages + 1):
        list_embed = discord.Embed(colour=destination.guild.me.colour)
        other_options = []
        emojified_options = []
        current_start = offset * len(options_emoji_list)
        current_options_emoji = options_emoji_list
        current_choices = choices_list[current_start:current_start + len(options_emoji_list)]
        try:
            if len(current_choices) < len(current_options_emoji):
                current_options_emoji = current_options_emoji[:len(current_choices)]
            for i, name in enumerate(current_choices):
                emojified_options.append(f"{current_options_emoji[i]}: {name}")
            prompt += '\n\n**Please wait until all reaction emoji are added before selecting any!**\n\n'
            list_embed.add_field(name=prompt, value='\n'.join(emojified_options), inline=False)
            embed_footer = "Choose the reaction corresponding to the desired entry above."
            if offset != num_pages:
                other_options.append(next_emoji)
                embed_footer += f" Select {next_emoji_text} to see more options."
            if allow_edit:
                other_options.append(edit_emoji)
                embed_footer += f" To enter a custom answer, select {edit_emoji_text}."
            embed_footer += f" Select {cancel_emoji} to cancel."
            if multiple:
                other_options.append(finish_multiple)
                embed_footer = f"Choose the reaction(s) corresponding to the desired entry above and select the {finish_multiple} to finish."
            else:
                other_options.append(cancel_emoji)
            list_embed.set_footer(text=embed_footer)
            q_msg = await destination.send(embed=list_embed)
            all_options = current_options_emoji + other_options
            reaction, __ = await ask(bot, q_msg, user_list, react_list=all_options, multiple=multiple)
        except TypeError:
            return None
        if not reaction:
            return None
        await q_msg.delete()
        if multiple:
            reactions = []
            for r in reaction:
                if r.emoji == cancel_emoji:
                    return None
                reactions.append(choices_list[current_start + current_options_emoji.index(r.emoji)])
            return reactions
        else:
            if reaction.emoji in current_options_emoji:
                return choices_list[current_start + current_options_emoji.index(reaction.emoji)]
        if reaction.emoji == edit_emoji:
            break
        if reaction.emoji == cancel_emoji:
            return None

    def check(message):
        if user_list:
            return (message.author.id in user_list)
        else:
            return (message.author.id != message.guild.me.id)

    try:
        await destination.send("What's the custom value?")
        message = await bot.wait_for('message', check=check, timeout=60)
        return message.content
    except Exception:
        return None


async def letter_case(iterable, find, *, limits=None):
    servercase_list = []
    lowercase_list = []
    for item in iterable:
        if not item.name:
            continue
        elif item.name and (not limits or item.name.lower() in limits):
            servercase_list.append(item.name)
            lowercase_list.append(item.name.lower())
    if find.lower() in lowercase_list:
        index = lowercase_list.index(find.lower())
        return servercase_list[index]
    else:
        return None


async def sleep_and_cleanup(messages, sleep_time):
    await asyncio.sleep(sleep_time)
    for message in messages:
        try:
            await message.delete()
        except:
            pass


def do_template(message, author, guild):
    not_found = []

    def template_replace(match):
        if match.group(3):
            if match.group(3) == 'user':
                return '{user}'
            elif match.group(3) == 'server':
                return guild.name
            else:
                return match.group(0)
        if match.group(4):
            emoji = (':' + match.group(4)) + ':'
            return parse_emoji(guild, emoji)
        match_type = match.group(1)
        full_match = match.group(0)
        match = match.group(2)
        if match_type == '<':
            mention_match = re.search('(#|@!?|&)([0-9]+)', match)
            match_type = mention_match.group(1)[0]
            match = mention_match.group(2)
        if match_type == '@':
            member = guild.get_member_named(match)
            if match.isdigit() and (not member):
                member = guild.get_member(match)
            if (not member):
                not_found.append(full_match)
            return member.mention if member else full_match
        elif match_type == '#':
            channel = discord.utils.get(guild.text_channels, name=match)
            if match.isdigit() and (not channel):
                channel = guild.get_channel(match)
            if (not channel):
                not_found.append(full_match)
            return channel.mention if channel else full_match
        elif match_type == '&':
            role = discord.utils.get(guild.roles, name=match)
            if match.isdigit() and (not role):
                role = discord.utils.get(guild.roles, id=int(match))
            if (not role):
                not_found.append(full_match)
            return role.mention if role else full_match

    template_pattern = '(?i){(@|#|&|<)([^{}]+)}|{(user|server)}|<*:([a-zA-Z0-9]+):[0-9]*>*'
    msg = re.sub(template_pattern, template_replace, message)
    return (msg, not_found)


# Convert an arbitrary string into something which
# is acceptable as a Discord channel name.

def sanitize_name(name):
    # Remove all characters other than alphanumerics,
    # dashes, underscores, and spaces
    ret = re.sub('[^a-zA-Z0-9 _\\-]', '', name)
    # Replace spaces with dashes
    ret = ret.replace(' ', '-')
    return ret


# Given a list of types, return a
# space-separated string of their type IDs,
# as defined in the type_id_dict
def types_to_str(guild, type_list, config):
    ret = ''
    for p_type in type_list:
        p_type = p_type.lower()
        x2 = ''
        if p_type[-2:] == 'x2':
            p_type = p_type[:-2]
            x2 = 'x2'
        p_type_name = 'k' + p_type
        p_id = config['type_id_dict'][p_type]
        # Append to string
        ret += f"<:{p_type_name}:{p_id}>" + x2
    return ret


# Given a string, if it fits the pattern :emoji name:,
# and <emoji_name> is in the server's emoji list, then
# return the string <:emoji name:emoji id>. Otherwise,
# just return the string unmodified.

def parse_emoji(guild, emoji_string):
    if (emoji_string[0] == ':') and (emoji_string[-1] == ':'):
        emoji = discord.utils.get(guild.emojis, name=emoji_string.strip(':'))
        if emoji:
            emoji_string = '<:{0}:{1}>'.format(emoji.name, emoji.id)
    return emoji_string


def simple_gmaps_query(lat, lng):
    return f'https://www.google.com/maps/search/?api=1&query={lat},{lng}'


async def time_to_minute_count(guild_dict, channel, timestr, error=True, current=None):
    if current and timestr.isdigit():
        now = datetime.datetime.utcnow() + datetime.timedelta(
            hours=guild_dict[channel.guild.id]['configure_dict']['settings']['offset'])
        current = current + datetime.timedelta(minutes=int(timestr))
        timediff = relativedelta(current, now)
        return (timediff.hours * 60) + timediff.minutes + 1
    if 'am' in timestr.lower():
        timestr = timestr.strip('am')
    if 'pm' in timestr.lower():
        timestr = timestr.strip('pm')
    if timestr.isdigit() and len(timestr) < 3:
        return int(timestr)
    if timestr.isdigit():
        timestr = timestr[:-2] + ':' + timestr[-2:]
    if ':' in timestr:
        now = datetime.datetime.utcnow() + datetime.timedelta(
            hours=guild_dict[channel.guild.id]['configure_dict']['settings']['offset'])
        start = dateparser.parse(timestr, settings={'PREFER_DATES_FROM': 'future'})
        start = start.replace(month=now.month, day=now.day, year=now.year)
        timediff = relativedelta(start, now)
        if timediff.hours <= -10:
            start = start + datetime.timedelta(hours=12)
            timediff = relativedelta(start, now)
        raidexp = (timediff.hours * 60) + timediff.minutes + 1
        if raidexp < 0:
            if error:
                await channel.send(embed=discord.Embed(
                    colour=discord.Colour.red(),
                    description='Please enter a time in the future.'))
            return False
        return raidexp
    else:
        if error:
            await channel.send(embed=discord.Embed(
                colour=discord.Colour.red(),
                description="I couldn't understand your time format."))
        return False


def parse_time_str(offset, timestr):
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=offset)
    start = dateparser.parse(timestr, settings={'PREFER_DATES_FROM': 'future'})
    start = start.replace(month=now.month, day=now.day, year=now.year)
    timediff = relativedelta(start, now)
    if timediff.hours <= -10:
        start = start + datetime.timedelta(hours=12)
    return start


async def prompt_match_result(Kyogre, channel, author_id, target, result_list):
    if not isinstance(result_list, list):
        result_list = [result_list]
    if not result_list or result_list[0] is None or result_list[0][0] is None:
        return None
    # quick check if a full match exists
    exact_match = [match for match, score in result_list if match.lower() == target.lower()]
    if len(exact_match) == 1:
        return exact_match[0]
    # reminder: partial, exact matches have 100 score, that's why this check exists
    perfect_scores = [match for match, score in result_list if score == 100]
    if len(perfect_scores) != 1:
        # one or more imperfect candidates only, ask user which to use
        sorted_result = sorted(result_list, key=lambda t: t[1], reverse=True)
        choices_list = [match for match, score in sorted_result]
        prompt = "Didn't find an exact match for '{0}'. {1} potential matches found.".format(target, len(result_list))
        match = await ask_list(Kyogre, prompt, channel, choices_list, user_list=author_id)
    else:
        # found a solitary best match
        match = perfect_scores[0]
    return match


async def reaction_delay(message, reacts, delay=0.25):
    for r in reacts:
        await asyncio.sleep(delay)
        await message.add_reaction(r)


def get_category(channel, level, guild_dict, category_type="raid"):
    guild = channel.guild
    if category_type == "raid" or category_type == "egg":
        report = "raid"
    else:
        report = category_type
    catsort = guild_dict[guild.id]['configure_dict'][report].get('categories', None)
    if catsort == "same":
        return channel.category
    elif catsort == "region":
        category = discord.utils.get(guild.categories,
                                     id=guild_dict[guild.id]['configure_dict'][report]['category_dict'][channel.id])
        return category
    elif catsort == "level":
        category = discord.utils.get(guild.categories,
                                     id=guild_dict[guild.id]['configure_dict'][report]['category_dict'][level])
        return category
    else:
        return None


def can_manage(user, config):
    if checks.is_user_dev_or_owner(config, user.id):
        return True
    for role in user.roles:
        if role.permissions.manage_messages:
            return True
    return False


def can_manage_lite(user, config):
    if checks.is_user_dev_or_owner(config, user.id):
        return True
    for role in user.roles:
        if role.permissions.manage_nicknames:
            return True
    return False


def can_edit_reports(user, config):
    can_edit = False
    for role in user.roles:
        if role.permissions.manage_nicknames:
            can_edit = True
            break
    return can_edit or can_manage(user, config)


def list_chunker(in_list, n):
    for i in range(0, len(in_list), n):
        yield in_list[i:i + n]


async def clone_and_position(channel, delete=False):
    position = channel.position
    new_channel = await channel.clone()
    await new_channel.edit(position=position)
    if delete:
        await channel.delete()
    return new_channel

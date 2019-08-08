import asyncio
import re

import discord
from discord.ext import commands

from kyogre import checks, utils

class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='embed')
    @checks.serverowner_or_permissions(manage_message=True)
    async def _embed(self, ctx, title, content=None, colour=None,
                     icon_url=None, image_url=None, thumbnail_url=None,
                     plain_msg=''):
        """Build and post an embed in the current channel.

        Note: Always use quotes to contain multiple words within one argument.
        """
        await ctx.embed(title=title, description=content, colour=colour,
                        icon=icon_url, image=image_url,
                        thumbnail=thumbnail_url, plain_msg=plain_msg)

    async def get_channel_by_name_or_id(self, ctx, name):
        channel = None
        # If a channel mention is passed, it won't be recognized as an int but this get will succeed
        name = utils.sanitize_name(name)
        try:
            channel = discord.utils.get(ctx.guild.text_channels, id=int(name))
        except ValueError:
            pass
        if not channel:
            channel = discord.utils.get(ctx.guild.text_channels, name=name)
        if channel:
            guild_channel_list = []
            for textchannel in ctx.guild.text_channels:
                guild_channel_list.append(textchannel.id)
            diff = set([channel.id]) - set(guild_channel_list)
        else:
            diff = True
        if diff:
            return None
        return channel

    def create_gmaps_query(self, details, channel, type="raid"):
        """Given an arbitrary string, create a Google Maps
        query using the configured hints"""
        if type == "raid" or type == "egg":
            report = "raid"
        else:
            report = type
        if "/maps" in details and "http" in details:
            mapsindex = details.find('/maps')
            newlocindex = details.rfind('http', 0, mapsindex)
            if newlocindex == -1:
                return
            newlocend = details.find(' ', newlocindex)
            if newlocend == -1:
                newloc = details[newlocindex:]
                return newloc
            else:
                newloc = details[newlocindex:newlocend + 1]
                return newloc
        details_list = details.split()
        # look for lat/long coordinates in the location details. If provided,
        # then channel location hints are not needed in the  maps query
        if re.match(r'^\s*-?\d{1,2}\.?\d*,\s*-?\d{1,3}\.?\d*\s*$',
                    details):  # regex looks for lat/long in the format similar to 42.434546, -83.985195.
            return "https://www.google.com/maps/search/?api=1&query={0}".format('+'.join(details_list))
        loc_list = self.bot.guild_dict[channel.guild.id]['configure_dict'][report]['report_channels'][channel.id].split()
        return 'https://www.google.com/maps/search/?api=1&query={0}+{1}'.format('+'.join(details_list),
                                                                                '+'.join(loc_list))

    @staticmethod
    async def reaction_delay(message, reacts, delay=0.25):
        for r in reacts:
            await asyncio.sleep(delay)
            await message.add_reaction(r)

def setup(bot):
    bot.add_cog(Utilities(bot))

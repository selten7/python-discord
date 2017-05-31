import logging
import os
import re
import sqlite3
import urllib.parse
import urllib.request

import discord
import requests
import toml

from bs4 import BeautifulSoup

from lolicon.command import Command
from lolicon.logger import l
from lolicon.user import User, DEFAULT_PERMISSIONS

USER_AGENT = 'Lolicon/master (https://github.com/selten7/python-lolicon)'

class WTF(Exception):
    pass

def init_database(db_file):
    l.debug('initializing database: %s', db_file)
    conn = sqlite3.connect(db_file)

    c = conn.cursor()

    c.execute('''create table meta (key text, value text)''')
    c.execute(
        '''insert into meta (key, value) values (?, ?)''',
        ('revision', '1')
    )

    c.execute('''create table permissions (user_id text, permission text, flag int)''')
    c.execute('''create table kudos (user_id text, kudos int)''')
    c.execute('''create table tags (server_id text, key text, value text)''')

    conn.commit()

    conn.close()

def upload_image(url, name):
    headers = {
        'User-Agent': USER_AGENT,
    }

    req = urllib.request.Request(
        url,
        headers=headers
    )
    f = urllib.request.urlopen(req)

    files = {
        'files[]': (name, f),
    }
    resp = requests.post(
        'https://nya.is/upload.php?output=json',
        files=files,
        headers=headers
    )

    data = resp.json()

    if not data['success']:
        return

    return data['files'][0]['url']

class Lolicon:

    def __init__(self, config_file):
        self.config_file = config_file

        self.client = None
        self.config = None
        self.db = None

        self.load()

    def load(self):
        if self.db:
            l.debug('committing changes to database')

            self.db.commit()
            self.db.close()

            self.db = None

        l.debug('loading config: %s', self.config_file)
        with open(self.config_file, 'r', encoding='utf-8') as f:
            raw_config = f.read()

        self.config = toml.loads(raw_config)

        db_dir = os.path.dirname(self.config_file)
        db_file = os.path.join(db_dir, self.config['bot']['data'])

        if not os.path.isfile(db_file):
            init_database(db_file)

        l.debug('connecting to db: %s', db_file)
        self.db = sqlite3.connect(db_file)

    def parse_user(self, message):
        member = message.author
        user_id = str(member.id)

        permissions = {}
        if user_id in self.config['bot']['mods']:
            for key in DEFAULT_PERMISSIONS:
                permissions[key] = True
        else:
            c = self.db.cursor()

            rows = c.execute(
                'select permission, flag from permissions where user_id = ?',
                (user_id,)
            )

            for row in rows:
                permissions[row[0]] = bool(row[1])

        user = User(id=user_id, permissions=permissions)

        return user

    def parse_command(self, message):
        prefix = self.config['bot']['prefix']
        line =  message.content

        if not line.startswith(prefix):
            return

        parts = line.split(maxsplit=1)

        name = parts[0][len(prefix):]
        if len(parts) > 1:
            trailing = parts[1]
        else:
            trailing = ''

        user = self.parse_user(message)

        return Command(name, trailing, user)

    async def on_ready(self):
        user = self.client.user

        l.info('logged in as %s (%s)', user.name, user.id)

    async def on_message(self, message):
        if message.author.bot:
            return

        server_id = message.server.id

        for part in message.content.split():
            if 'illust_id=' in part and part.startswith('http'):
                split = urllib.parse.urlsplit(part)
                if split.scheme not in ('http', 'https'):
                    continue
                if split.netloc != 'www.pixiv.net':
                    continue
                if split.path != '/member_illust.php':
                    continue
                q = dict(urllib.parse.parse_qsl(split.query))
                if 'illust_id' not in q:
                    continue

                resp = urllib.request.urlopen(part)
                soup = BeautifulSoup(resp.read(), 'lxml')
                meta = soup.select('[property="og:image"]')
                if not meta:
                    continue

                image_url = meta[0]['content']

                em = discord.Embed()
                em.set_image(url=image_url)

                await self.client.send_message(message.channel, embed=em)

        cmd = self.parse_command(message)
        if not cmd:
            return

        user = cmd.user

        #
        # Command aliases.
        #
        if cmd.name in ('tag', 'tags') and not cmd.trailing:
            cmd.name = 'tag'
            cmd.trailing = 'list'

        #
        # Command handling.
        #
        if cmd.name == 'help':
            prefix = self.config['bot']['prefix']

            embed = discord.Embed(
                title='Lolicon',
                description='List of commands supported by Lolicon',
                url='https://github.com/selten7/python-lolicon',
                type='rich'
            )

            embed.set_thumbnail(url='https://raw.githubusercontent.com/selten7/python-lolicon/master/media/embed-thumbnail.png')

            embed.add_field(
                name=prefix + 'help',
                value='Show this help message',
                inline=False
            )

            if user.has_permission('use_tags'):
                embed.add_field(
                    name=prefix + '!<name>',
                    value='Display the value for the tag `<name>`.',
                    inline=False
                )

            if user.has_permission('modify_tags'):
                embed.add_field(
                    name=prefix + 'tag set <name> <value>',
                    value='Set `<value>` to the tag `<name>`. `<name>` must not contain spaces.',
                    inline=False
                )

                embed.add_field(
                    name=prefix + 'tag del <name>',
                    value='Delete the tag `<name>`.',
                    inline=False
                )

            if user.has_permission('kudos'):
                embed.add_field(
                    name=prefix + 'kudos <user>',
                    value='Add 1 "kudo" to `<user>` (must be a mention).',
                    inline=False
                )

                embed.add_field(
                    name=prefix + 'damedesu <user>',
                    value='Remove 1 "kudo" from `<user>` (must be a mention).',
                    inline=False
                )

            await self.client.send_message(message.channel, embed=embed)
        elif cmd.name == 'ping' and user.has_permission('ping'):
            await self.client.send_message(message.channel, 'pong')
        elif cmd.name == 'tag':
            args = cmd.trailing.split()
            if not args:
                return

            if len(args) == 1 and args[0] == 'list' and user.has_permission('use_tags'):
                c = self.db.cursor()

                rows = c.execute(
                    '''select key from tags where server_id = ?''',
                    (server_id,)
                )

                tags = ['`{}`'.format(row[0]) for row in rows]
                if tags:
                    response = ', '.join(tags)
                else:
                    response = 'No tags found.'

                await self.client.send_message(message.channel, response)
            elif len(args) >= 2 and args[0] == 'set' and user.has_permission('modify_tags'):
                key = args[1]

                if len(args) == 2 and user.has_permission('upload'):
                    images = []
                    for attachment in message.attachments:
                        filename = attachment['filename']
                        if os.path.splitext(filename)[1] not in ('.png', '.jpg', '.jpeg', '.gif'):
                            continue

                        image_url = attachment['url']
                        images.append((image_url, filename))

                    results = []
                    for (image_url, name) in images:
                        result_url = upload_image(image_url, name)
                        if not result_url:
                            await self.client.send_message(message.channel, 'Could not upload images.')
                            return

                        results.append(result_url)

                    cmd.trailing += ' '
                    cmd.trailing += ' '.join(results)
                    args = cmd.trailing.split()

                if len(args) >= 3:
                    value = cmd.trailing.split(maxsplit=2)[2]

                    if key.startswith('`') and key.endswith('`'):
                        key = key[1:-1]

                    if not re.match(r'^[a-z0-9_\.\!\?\-]+$', key):
                        await self.client.send_message(
                            message.channel,
                            'Invalid key. You can only use lowercase letters, numbers, `_`, `.`, `!`, `?` and `-`.'
                        )
                        return

                    c = self.db.cursor()

                    c.execute(
                        '''delete from tags where server_id = ? and key = ?''',
                        (server_id, key)
                    )
                    c.execute(
                        '''insert into tags (server_id, key, value) values (?, ?, ?)''',
                        (server_id, key, value)
                    )

                    self.db.commit()

                    await self.client.send_message(
                        message.channel,
                        'Tag **{}** saved successfully'.format(key)
                    )
            elif len(args) >= 2 and args[0] in ('del', 'delete', 'remove') and user.has_permission('modify_tags'):
                tags = args[1:]

                for (i, tag) in enumerate(tags):
                    if tag.startswith('`') and tag.endswith('`'):
                        tags[i] = tag[1:-1]

                for key in tags:
                    c = self.db.cursor()

                    c.execute(
                        '''delete from tags where server_id = ? and key = ?''',
                        (server_id, key)
                    )

                self.db.commit()

                await self.client.send_message(message.channel, ':ok_hand:')

        elif cmd.name.startswith('!') and user.has_permission('use_tags'):
            tagname = cmd.name[1:]

            c = self.db.cursor()
            rows = c.execute(
                '''select value from tags where server_id = ? and key = ?''',
                (server_id, tagname)
            )
            for row in rows:
                await self.client.send_message(message.channel, row[0])
                break
            else:
                await self.client.send_message(message.channel, 'Tag **{}** not found.'.format(
                    tagname
                ))
        elif cmd.name == 'kick' and user.has_permission('kick'):
            for mention in message.mentions:
                await self.client.kick(mention)
        elif cmd.name == 'ban' and user.has_permission('ban'):
            for mention in message.mentions:
                await self.client.ban(mention)
        elif cmd.name in ('kudos', 'damedesu') and user.has_permission('kudos'):
            targets = {str(mention.id): mention for mention in message.mentions}
            if not targets:
                return

            mentioned_users = {}

            c = self.db.cursor()
            for target_id in targets:
                result = c.execute(
                    '''select kudos from kudos where user_id = ?''',
                    (target_id,)
                )
                rows = list(result)
                if not rows:
                    c.execute(
                        '''insert into kudos (user_id, kudos) values (?, ?)''',
                        (target_id, 0)
                    )

                if cmd.name == 'kudos':
                    op = '+'
                elif cmd.name == 'damedesu':
                    op = '-'
                else:
                    raise WTF()

                c.execute(
                    '''update kudos set kudos = kudos {} 1 where user_id = ?'''.format(
                        op
                    ),
                    (target_id,)
                )

            response_lines = []
            rows = c.execute(
                '''select user_id, kudos from kudos where {}'''.format(
                    ' or '.join(['user_id = ?']*len(targets))
                ),
                tuple(targets.keys())
            )
            for row in rows:
                response_lines.append('**{}** has now **{}** kudo{}!'.format(
                    targets[row[0]].name,
                    row[1],
                    '' if row[1] == 1 else 's'
                ))

            self.db.commit()

            await self.client.send_message(
                message.channel,
                '\n'.join(
                    sorted(response_lines)
                )
            )

    def run(self):
        self.client = discord.Client()

        self.client.event(self.on_ready)
        self.client.event(self.on_message)

        token = self.config['discord']['token']

        self.client.run(token)

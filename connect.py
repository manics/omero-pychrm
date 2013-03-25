#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2013 University of Dundee & Open Microscopy Environment.
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

# Shortcut for connecting to OMERO servers
#
# To use this rename servers.conf.example to servers.conf in the current
# directory, and edit:
#
# #name host      port username password
# local localhost 4064 test1    test1
#
# In ipython you can run
# > import connect
# > co = connect.XXX()
# to connect, where XXX is one of the shortnames in the servers.conf

import omero
import omero.gateway
import os.path


class Connection:
    def __init__(self, user, passwd, host, port, keepAlive):
        self.user = user
        self.passwd = passwd
        self.host = host
        self.port = port
        self.keepAlive = keepAlive
        self.cli = None
        self.c()

    def c(self):
        self.close()
        self.cli = omero.client(host=self.host, port=self.port)
        self.sess = self.cli.createSession(self.user, self.passwd)
        self.cli.enableKeepAlive(self.keepAlive)
        self.conn = omero.gateway.BlitzGateway(client_obj=self.cli)
        self.res = self.sess.sharedResources()

    def close(self):
        if self.cli:
            self.cli.closeSession()


def _readServers(file):
    cfg = {}
    with open(file) as f:
        try:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                v = line.split()
                if len(v) != 5:
                    raise Exception('Invalid line: "%s"' % line)
                print v
                cfg[v[0]] = { 'host': v[1], 'port': int(v[2]),
                              'user': v[3], 'passwd': v[4]     }
        except IOError:
            pass

    return cfg


def _makeFunction(v):
    def f(user=v['user'], passwd=v['passwd'], host=v['host'], port=v['port'],
          keepAlive=60):
        return Connection(user, passwd, host, port, keepAlive)
    return f

# Read servers.conf in the directory containing this script
_cfg = _readServers(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                 'servers.conf'))
for _k in _cfg:
    vars()[_k] = _makeFunction(_cfg[_k])

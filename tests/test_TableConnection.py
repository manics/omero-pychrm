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

#
#

import sys
if sys.version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest

import omero
from omero.rtypes import unwrap
import collections

import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'OmeroWndcharm'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from TableConnection import Connection, TableConnection, FeatureTableConnection


class ClientHelper(unittest.TestCase):

    def create_client(self):
        cli = omero.client()
        sess = cli.createSession()
        return (cli, sess)

    def setUp(self):
        """
        Create a connection for creating the test tables.
        ICE_CONFIG must be set.
        """
        self.cli, self.sess = self.create_client()
        self.tableName = '/test_TableConnection/test.h5'

    def tearDown(self):
        self.cli.closeSession()


class TestConnection(ClientHelper):
    class TestWith(Connection):
        def __init__(self, client):
            super(TestConnection.TestWith, self).__init__(client=client)
            self.x = 1

        def close(self):
            self.x = 0
            super(TestConnection.TestWith, self).close()

    def test_enterExitWith(self):
        cli, sess = self.create_client()
        with TestConnection.TestWith(client=cli) as c:
            self.assertEquals(c.x, 1)
        self.assertEquals(c.x, 0)


class TestTableConnection(ClientHelper):

    def create_table(self):
        t = self.sess.sharedResources().newTable(0, self.tableName)
        cols = [omero.grid.LongColumn('lc1', 'l c 1', [1, 2, 3, 4])]
        t.initialize(cols)
        t.addData(cols)
        tid = unwrap(t.getOriginalFile().getId())
        t.close()
        return tid

    def test_openTable(self):
        tid = self.create_table()

        tc = TableConnection(client=self.cli, tableName=self.tableName)
        t = tc.openTable(tid)
        self.assertIsNotNone(t)

        t.close()

    def test_findByName(self):
        tid = self.create_table()

        tc = TableConnection(client=self.cli, tableName=self.tableName)
        found = False
        for ofiles in tc.findByName():
            found = found or unwrap(ofiles.getId()) == tid
        self.assertTrue(found)

        tc.close()

    def deleteAllTables(self):
        """
        Don't run unless explicitly requested.
        Doesn't seem to work.
        """
        tc = TableConnection(client=self.cli, tableName=self.tableName)
        tc.deleteAllTables()
        ofiles = list(tc.findByName())
        self.assertEqual(len(ofiles), 0)

    def test_headersRows(self):
        tid = self.create_table()
        tc = TableConnection(client=self.cli)
        t = tc.openTable(tid)

        headers = tc.getHeaders()
        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0].name, 'lc1')
        # It looks like descriptions aren't returned?????
        #self.assertEqual(headers[0].description, 'l c 1')
        self.assertEqual(tc.getNumberOfRows(), 4)

    def test_newTable(self):
        tc = TableConnection(client=self.cli, tableName=self.tableName)
        cols = [omero.grid.LongColumn('lc1', 'l c 1', [1, 2, 3])]
        t = tc.newTable(cols)
        self.assertIsNotNone(t)

    def test_chunked(self):
        tid = self.create_table()
        tc = TableConnection(client=self.cli, tableName=self.tableName)
        t = tc.openTable(tid)

        cols = tc.getHeaders()
        cols[0].values = [5, 6]
        n = tc.chunkedAddData(cols, 1)
        self.assertEqual(n, 2)

        data = tc.chunkedRead([0], 1, 6, 3)
        self.assertEqual(len(data.columns), 1)
        self.assertEqual(data.columns[0].values, [2, 3, 4, 5, 6])

        tc.close()



class TestFeatureTableConnection(ClientHelper):

    def create_table(self):
        cli, sess = self.create_client()
        ftc = FeatureTableConnection(client=cli, tableName=self.tableName)
        desc = [('a', 3), ('b', 1)]
        ftc.createNewTable('ID', desc)
        tid = ftc.tableId
        ftc.close()
        return tid

    def create_table_with_data(self):
        cli, sess = self.create_client()
        ftc = FeatureTableConnection(client=cli, tableName=self.tableName)
        desc = [('a', 3), ('b', 1)]
        ftc.createNewTable('ID', desc)

        cols = ftc.getHeaders()
        cols[0].values = [1, 8, 3, 6]
        cols[1].values = [[], [1., 2., 3.], [4., 5., 6.], []]
        cols[2].values = [[7.], [], [8.], []]
        ftc.addData(cols)

        tid = ftc.tableId
        ftc.close()
        return tid


    def test_createNewTable(self):
        tid = self.create_table()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        headers = ftc.table.getHeaders()
        self.assertEqual(len(headers), 6)
        self.assertEqual([h.name for h in headers[:3]], ['ID', 'a', 'b'])
        self.assertEqual([h.name for h in headers[3:]],
                         ['_b_ID', '_b_a', '_b_b'])

    def test_isValid(self):
        tid = self.create_table_with_data()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)
        bs = ftc.isValid([2, 0, 1], 0, 4)

        self.assertEqual(bs[1].values, [True, True, True, True])
        self.assertEqual(bs[2].values, [False, True, True, False])
        self.assertEqual(bs[0].values, [True, False, True, False])

    def test_readSubArray(self):
        tid = self.create_table_with_data()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        can = {1:[0,2], 2:[0]}
        xs = ftc.readSubArray(can, 0, 4)
        self.assertEqual(xs[0].values, [[], [1., 3.], [4., 6.], []])
        self.assertEqual(xs[1].values, [[7.], [], [8.], []])

    @unittest.skipIf(not hasattr(collections, 'OrderedDict'),
                     "OrderedDict not available in Python < 2.7")
    def test_readSubArray_ordered(self):
        tid = self.create_table_with_data()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        can = collections.OrderedDict([(2, [0]), (1, [0,2])])
        xs = ftc.readSubArray(can, 0, 4)
        self.assertEqual(xs[1].values, [[], [1., 3.], [4., 6.], []])
        self.assertEqual(xs[0].values, [[7.], [], [8.], []])

    def test_readArray(self):
        tid = self.create_table_with_data()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        xs = ftc.readArray([0, 2], 0, 3, chunk=2)
        self.assertEqual(xs[0].values, [1, 8, 3])
        self.assertEqual(xs[1].values, [[7.], [], [8.]])

        xs = ftc.readArray([2, 0, 1], 0,
                           ftc.getNumberOfRows(), chunk=3)
        self.assertEqual(xs[1].values, [1, 8, 3, 6])
        self.assertEqual(xs[2].values, [[], [1., 2., 3.], [4., 5., 6.], []])
        self.assertEqual(xs[0].values, [[7.], [], [8.], []])

    def test_getRowId(self):
        tid = self.create_table_with_data()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        self.assertEqual(ftc.getRowId(1), 0)
        self.assertEqual(ftc.getRowId(3), 2)
        self.assertEqual(ftc.getRowId(6), 3)
        self.assertEqual(ftc.getRowId(8), 1)
        self.assertIsNone(ftc.getRowId(1000))

    def test_getHeaders(self):
        tid = self.create_table()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        headers = ftc.getHeaders()
        self.assertEqual(len(headers), 3)
        self.assertEqual([h.name for h in headers], ['ID', 'a', 'b'])

    def test_addData(self):
        tid = self.create_table_with_data()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        cols = ftc.getHeaders()
        cols[0].values = [2, 4]
        cols[1].values = [[11., 12., 13.], [14., 15., 16.]]
        cols[2].values = [[17.], [18.]]
        ftc.addData(cols)

        xs = ftc.readArray(range(len(ftc.getHeaders())), 0,
                           ftc.getNumberOfRows(), chunk=4)
        self.assertEqual(xs[0].values, [1, 8, 3, 6, 2, 4])
        self.assertEqual(xs[1].values, [[], [1., 2., 3.], [4., 5., 6.], [],
                                        [11., 12., 13.], [14., 15., 16.]])
        self.assertEqual(xs[2].values, [[7.], [], [8.], [], [17.], [18.]])

    def test_addPartialData(self):
        tid = self.create_table_with_data()
        ftc = FeatureTableConnection(client=self.cli, tableName=self.tableName)
        ftc.openTable(tid)

        cols = ftc.getHeaders()
        cols = [cols[2], cols[0]]
        cols[1].values = [2, 4]
        cols[0].values = [[], [18.]]
        ftc.addPartialData(cols)

        xs = ftc.readArray(range(len(ftc.getHeaders())), 0,
                           ftc.getNumberOfRows(), chunk=4)
        self.assertEqual(xs[0].values, [1, 8, 3, 6, 2, 4])
        self.assertEqual(xs[1].values, [[], [1., 2., 3.], [4., 5., 6.], [],
                                        [], []])
        self.assertEqual(xs[2].values, [[7.], [], [8.], [], [], [18.]])


if __name__ == '__main__':
    unittest.main()

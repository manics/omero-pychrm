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

import uuid
import omero
from omero.rtypes import wrap, unwrap
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'OmeroWndcharm'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import WndcharmStorage
from WndcharmStorage import FeatureTable, ClassifierTables


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
        self.tableName = '/test_WndcharmStorage/test.h5'
        self.conn = omero.gateway.BlitzGateway(client_obj=self.cli)

    def tearDown(self):
        self.cli.closeSession()

    def delete(self, delType, objId):
        try:
            n = len(objId)
        except TypeError:
            objId = [objId]
            n = 1
        handle = self.conn.deleteObjects(delType, objId, True, True)
        try:
            self.conn._waitOnCmd(handle)
            rs = handle.getResponse().responses
            self.assertEqual(len(rs), n)
            if rs[0].scheduledDeletes != rs[0].actualDeletes:
                print 'Deletes scheduled:%d actual:%d' % (
                    rs[0].scheduledDeletes, rs[0].actualDeletes)
        finally:
            handle.close()

    def getObject(self, objType, objId):
        q = 'from %s o where o.id=:id' % objType
        p = omero.sys.ParametersI()
        p.map['id'] = wrap(objId)
        obj = self.conn.getQueryService().findByQuery(q, p)
        return obj


def unwrapVersion(vertag):
    return unwrap(vertag.getTextValue())


class TestFeatures(object):
    def __init__(self, inc = 0):
        self.names = ['a [0]', 'a [1]', 'b [0]']
        self.values = map(lambda x: x + inc, [10., 11., 12.])


class TestWndcharmStorage(unittest.TestCase):

    def test_parseFeatureName(self):
        r = WndcharmStorage.parseFeatureName('a b [321]')
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0], 'a b')
        self.assertEqual(r[1], 321)

    def createFeatureName(self):
        r = WndcharmStorage.createFeatureName('a b', 321)
        self.assertEqual(r, 'a b [321]')

    def featureSizes(self):
        ftsz = WndcharmStorage.featureSizes(['a b [12]', 'c d [3]', 'a b [14]'])
        self.assertEqual(len(ftsz.keys), 2)
        self.assertIn(ftsz, 'a b')
        self.assertIn(ftsz, 'c d')
        self.assertEqual(ftsz['a b'], 14)
        self.assertEqual(ftsz['c d'], 3)


class FeatureTableHelper(ClientHelper):

    def setUp(self):
        super(FeatureTableHelper, self).setUp()
        self.version = '%d.%d' % (
            int(uuid.uuid1().get_hex(), 16), int(uuid.uuid1().get_hex(), 16))
        self.otherversion = '%d.%d' % (
            int(uuid.uuid1().get_hex(), 16), int(uuid.uuid1().get_hex(), 16))

    def tearDown(self):
        handle = None
        try:
            qs = self.conn.getQueryService()
            p = omero.sys.ParametersI()
            p.map['vs'] = wrap(self.version)
            vertags = qs.findByQuery(
                'from TagAnnotation a where a.textValue=:vs', p)
            if vertags:
                handle = self.conn.deleteObjects(
                    'Annotation', [unwrap(vertags.id)])
                self.conn._waitOnCmd(handle)
        finally:
            if handle:
                handle.close()

        super(FeatureTableHelper, self).tearDown()


class TestFeatureTable(FeatureTableHelper):

    def setUp(self):
        super(TestFeatureTable, self).setUp()

    def create_table(self):
        cli, sess = self.create_client()
        ft = FeatureTable(client=cli, tableName=self.tableName)
        fts = ['a [0]', 'a [1]', 'b [0]']
        ft.createTable(fts, version=self.version)
        tid = ft.tc.tableId
        ft.close()
        return tid

    def create_table_with_data(self):
        cli, sess = self.create_client()
        ft = FeatureTable(client=cli, tableName=self.tableName)
        fts = ['a [0]', 'a [1]', 'b [0]']
        ft.createTable(fts, version=self.version)

        cols = ft.tc.getHeaders()
        cols[0].values = [7, 8]
        cols[1].values = [[1., 2.], [3., 4.]]
        cols[2].values = [[5.], [6.]]
        ft.tc.addData(cols)

        tid = ft.tc.tableId
        ft.close()
        return tid


    def test_createTable(self):
        tid = self.create_table()
        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        ft.openTable(tid)
        self.assertEqual(self.version, unwrapVersion(ft.versiontag))

        vertag = WndcharmStorage.getVersion(ft.conn, 'OriginalFile', tid)
        self.assertEqual(self.version, unwrapVersion(vertag))

        headers = ft.tc.getHeaders()
        self.assertEqual(len(headers), 3)
        self.assertEqual([h.name for h in headers], ['id', 'a', 'b'])
        self.assertEqual([h.size for h in headers[1:]], [2, 1])

    def test_annotateAndAnnotated(self):
        # There's a bug somewhere which means annotating the table with the
        # version annotation, then using the table as a FileAnnotation on
        # an object, causes the version annotation to be lost
        # Closing and reopening the table seems to work (see
        # FeatureTable.createTable)
        cli, sess = self.create_client()
        ft = FeatureTable(client=cli, tableName=self.tableName)
        fts = ['a [0]', 'a [1]', 'b [0]']
        ft.createTable(fts, version=self.version)
        tid = ft.tc.tableId

        self.assertEqual(self.version, unwrapVersion(ft.versiontag))

        vertag = WndcharmStorage.getVersion(ft.conn, 'OriginalFile', tid)
        self.assertEqual(self.version, unwrapVersion(vertag))

        p = omero.model.ProjectI()
        p.setName(wrap('tmp'))
        p = self.sess.getUpdateService().saveAndReturnObject(p)
        pid = unwrap(p.getId())
        p = ft.conn.getObject('Project', pid)
        WndcharmStorage.addFileAnnotationTo(ft.tc, p)

        vertag = WndcharmStorage.getVersion(ft.conn, 'OriginalFile', tid)
        self.assertEqual(self.version, unwrapVersion(vertag))
        self.delete('/Project', pid)
        self.delete('/OriginalFile', tid)

    def test_openTable(self):
        # The any version is handled by test_createTable() so just test the
        # specific version
        tid = self.create_table()
        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        ft.openTable(tid)
        self.assertEqual(self.version, unwrapVersion(ft.versiontag))
        ft.close()

        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        self.assertRaises(
            WndcharmStorage.WndcharmStorageError, ft.openTable,
            tid, self.otherversion)

    def test_isTableCompatible(self):
        tid = self.create_table()
        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        t = ft.openTable(tid, self.version)

        fts = TestFeatures()
        self.assertTrue(ft.isTableCompatible(fts))
        fts.names.append('a [2]')
        fts.values.append(13.)
        self.assertFalse(ft.isTableCompatible(fts))

    def test_tableContainsId(self):
        tid = self.create_table_with_data()
        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        ft.openTable(tid)
        self.assertTrue(ft.tableContainsId(7))

    def test_saveFeatures(self):
        tid = self.create_table_with_data()
        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        ft.openTable(tid)
        fts = TestFeatures()
        ft.saveFeatures(101, fts)

        self.assertEqual(ft.tc.getNumberOfRows(), 3)
        xs = ft.tc.readArray([0, 1, 2], 0, 4, chunk=3)
        self.assertEqual(xs[0].values, [7, 8, 101])
        self.assertEqual(xs[1].values, [[1., 2.], [3., 4.], [10., 11.]])
        self.assertEqual(xs[2].values, [[5.], [6.], [12.]])

    def test_loadFeatures(self):
        tid = self.create_table_with_data()
        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        ft.openTable(tid)

        names, values = ft.loadFeatures(7)
        self.assertEqual(names, ['a [0]', 'a [1]', 'b [0]'])
        self.assertEqual(values, [1., 2., 5.])

        names, values = ft.loadFeatures(8)
        self.assertEqual(names, ['a [0]', 'a [1]', 'b [0]'])
        self.assertEqual(values, [3., 4., 6.])

    def test_bulkLoadFeatures(self):
        tid = self.create_table_with_data()
        ft = FeatureTable(client=self.cli, tableName=self.tableName)
        ft.openTable(tid)

        names, values, ids = ft.bulkLoadFeatures()
        self.assertEqual(names, ['a [0]', 'a [1]', 'b [0]'])
        self.assertEqual(values, [[1., 2., 5.], [3., 4., 6.]])
        self.assertEqual(ids, [7, 8])


class TestClassifierTables(FeatureTableHelper):

    def setUp(self):
        super(TestClassifierTables, self).setUp()
        self.tableNameF = '/test_WndcharmStorage/ClassFeatures.h5'
        self.tableNameW = '/test_WndcharmStorage/Weights.h5'
        self.tableNameL = '/test_WndcharmStorage/ClassLabels.h5'

    def create_classifierTables(self):
        cli, sess = self.create_client()
        ct = ClassifierTables(cli, self.tableNameF, self.tableNameW,
                              self.tableNameL)
        return ct

    def checkEmptyClassifierTables(self, ct):
        headers = ct.tcF.getHeaders()
        self.assertEqual([h.name for h in headers],
                         ['id', 'label', 'features'])

        headers = ct.tcW.getHeaders()
        self.assertEqual([h.name for h in headers], ['featurename', 'weight'])

        headers = ct.tcL.getHeaders()
        self.assertEqual([h.name for h in headers], ['classID', 'className'])

    def checkClassifierTablesVersion(self, ct):
        self.assertEqual(unwrapVersion(ct.versiontag), self.version)

        verF = WndcharmStorage.getVersion(
            ct.tcF.conn, 'OriginalFile', ct.tcF.tableId)
        self.assertEqual(unwrapVersion(verF), self.version)

        verW = WndcharmStorage.getVersion(
            ct.tcW.conn, 'OriginalFile', ct.tcW.tableId)
        self.assertEqual(unwrapVersion(verW), self.version)

        verL = WndcharmStorage.getVersion(
            ct.tcL.conn, 'OriginalFile', ct.tcL.tableId)
        self.assertEqual(unwrapVersion(verL), self.version)


    def test_openTables(self):
        ct = self.create_classifierTables()
        fts = TestFeatures()
        ct.createClassifierTables(fts.names, self.version)
        tidF, tidW, tidL = ct.tcF.tableId, ct.tcW.tableId, ct.tcL.tableId
        ct.close()

        ct = self.create_classifierTables()
        ct.openTables(tidF, tidW, tidL)
        self.checkEmptyClassifierTables(ct)
        self.checkClassifierTablesVersion(ct)
        ct.close()

        ct = self.create_classifierTables()
        self.assertRaises(
            WndcharmStorage.WndcharmStorageError, ct.openTables, tidF, tidW, tidL,
            self.otherversion)

    def test_createClassifierTables(self):
        ct = self.create_classifierTables()
        fts = TestFeatures()
        ct.createClassifierTables(fts.names, self.version)
        self.checkEmptyClassifierTables(ct)
        self.checkClassifierTablesVersion(ct)

    def test_saveClassifierTables(self):
        ct = self.create_classifierTables()
        fts0 = TestFeatures()
        fts1 = TestFeatures(10)
        ct.createClassifierTables(fts0.names, self.version)
        self.checkClassifierTablesVersion(ct)

        ids = [7, 8]
        classIds = [1, 0]
        featureMatrix = [fts0.values, fts1.values]
        featureNames = fts0.names
        weights = [0.125, 0.375, 0.5]
        classNames = ['Cat', 'Hedgehog']
        ct.saveClassifierTables(ids, classIds, featureMatrix,
                                featureNames, weights, classNames)

        self.checkClassifierTablesVersion(ct)

        self.assertEqual(ct.tcF.getNumberOfRows(), 2)
        self.assertEqual(ct.tcW.getNumberOfRows(), 3)
        self.assertEqual(ct.tcL.getNumberOfRows(), 2)

        d = ct.tcF.table.readCoordinates([0, 1])
        self.assertEqual(d.columns[0].values, [7, 8])
        self.assertEqual(d.columns[1].values, [1, 0])
        self.assertEqual(d.columns[2].values,
                         [[10., 11., 12.], [20., 21., 22.]])

        d = ct.tcW.table.readCoordinates([0, 1, 2])
        self.assertEqual(d.columns[0].values, ['a [0]', 'a [1]', 'b [0]'])
        self.assertEqual(d.columns[1].values, [0.125, 0.375, 0.5])

        d = ct.tcL.table.readCoordinates([0, 1])
        self.assertEqual(d.columns[0].values, [0, 1])
        self.assertEqual(d.columns[1].values, ['Cat', 'Hedgehog'])

    def test_loadClassifierTables(self):
        ct = self.create_classifierTables()
        fts0 = TestFeatures()
        fts1 = TestFeatures(10)
        ct.createClassifierTables(fts0.names, self.version)
        self.checkClassifierTablesVersion(ct)

        ids = [7, 8]
        classIds = [1, 0]
        featureMatrix = [fts0.values, fts1.values]
        featureNames = fts0.names
        weights = [0.125, 0.375, 0.5]
        classNames = ['Cat', 'Hedgehog']
        ct.saveClassifierTables(ids, classIds, featureMatrix,
                                featureNames, weights, classNames)

        data = ct.loadClassifierTables()
        self.checkClassifierTablesVersion(ct)

        self.assertEqual(data['ids'], [7, 8])
        self.assertEqual(data['trainClassIds'], [1, 0])
        self.assertEqual(data['featureMatrix'],
                         [[10., 11., 12.], [20., 21., 22.]])
        self.assertEqual(data['featureNames'], ['a [0]', 'a [1]', 'b [0]'])
        self.assertEqual(data['weights'], [0.125, 0.375, 0.5])
        self.assertEqual(data['classIds'], [0, 1])
        self.assertEqual(data['classNames'], ['Cat', 'Hedgehog'])


class TestAnnotations(ClientHelper):
    class Tc:
        def __init__(self, conn):
            self.conn = conn
            self.tableName = '/test.h5'
            self.table = self.conn.getSharedResources().newTable(
                0, self.tableName)
            self.table.initialize([omero.grid.LongColumn('lc')])

        def close(self):
            self.table.close()

    def setUp(self):
        super(TestAnnotations, self).setUp()
        self.version = '%d.%d' % (
            int(uuid.uuid1().get_hex(), 16), int(uuid.uuid1().get_hex(), 16))

    def create_project(self, name):
        p = omero.model.ProjectI()
        p.setName(wrap(name))
        p = self.sess.getUpdateService().saveAndReturnObject(p)
        return unwrap(p.getId())

    def create_tag(self, name, ns=None):
        t = omero.model.TagAnnotationI()
        t.setTextValue(wrap(name))
        if ns is not None:
            t.setNs(wrap(ns))
        t = self.sess.getUpdateService().saveAndReturnObject(t)
        return unwrap(t.getId())

    def create_table(self):
        t = self.sess.sharedResources().newTable(0, '/test.h5')
        t.initialize([omero.grid.LongColumn('lc')])
        t.close()
        return unwrap(t.getOriginalFile().getId())

    def test_getVersion(self):
        version = str(uuid.uuid1())
        tableid = self.create_table()
        file = omero.model.OriginalFileI(tableid, False)
        version = str(uuid.uuid1())
        tagid = self.create_tag(version, WndcharmStorage.WNDCHARM_VERSION_NAMESPACE)
        tag = omero.model.TagAnnotationI(tagid, False)
        link = omero.model.OriginalFileAnnotationLinkI()
        link.setChild(tag)
        link.setParent(file)
        link = self.sess.getUpdateService().saveAndReturnObject(link)

        retrieved = WndcharmStorage.getVersion(
            self.conn, 'OriginalFile', unwrap(file.getId()))
        self.assertEqual(unwrapVersion(retrieved), version)

    #def test_getVersionAnnotation(self):
    #def test_createVersionAnnotation(self):
    #def test_getVersion(self):
    def test_versionAnnotation(self):
        version = str(uuid.uuid1())
        created = WndcharmStorage.createVersionAnnotation(self.conn, version)
        retrieved = WndcharmStorage.getVersionAnnotation(self.conn, version)

        self.assertEqual(unwrap(created.getNs()),
                         WndcharmStorage.WNDCHARM_VERSION_NAMESPACE)
        self.assertEqual(unwrapVersion(created), version)
        self.assertEqual(unwrap(retrieved.getNs()),
                         WndcharmStorage.WNDCHARM_VERSION_NAMESPACE)
        self.assertEqual(unwrapVersion(retrieved), version)

        pid = self.create_project('versionAnnotation')
        self.assertIsNone(WndcharmStorage.getVersion(self.conn, 'Project', pid))

        WndcharmStorage.addTagTo(self.conn, retrieved, 'Project', pid)
        a = WndcharmStorage.getVersion(self.conn, 'Project', pid)
        self.assertEqual(unwrap(a.getNs()),
                         WndcharmStorage.WNDCHARM_VERSION_NAMESPACE)
        self.assertEqual(unwrapVersion(a), version)

        self.delete('/Project', pid)
        # Note this should also delete the tag

    def test_assertVersionMatch(self):
        class MockVersion:
            def __init__(self, version):
                self.version = version

            def getTextValue(self):
                return self.version

        v1 = MockVersion('12.345')
        v2 = MockVersion('12.345')
        v3 = MockVersion('543.21')

        WndcharmStorage.assertVersionMatch(v1, v2)
        WndcharmStorage.assertVersionMatch(v1, v2.getTextValue())
        WndcharmStorage.assertVersionMatch(v1.getTextValue(), v2)
        self.assertRaises(
            WndcharmStorage.WndcharmStorageError, WndcharmStorage.assertVersionMatch,
            v1, v3)

    def test_addFileAnnotationTo(self):
        pid = self.create_project('addFileAnnotationTo')
        p = self.conn.getObject('Project', pid)
        tc = self.Tc(self.conn)
        fid = unwrap(tc.table.getOriginalFile().getId())
        WndcharmStorage.addFileAnnotationTo(tc, p)

        proj = self.conn.getObject('Project', pid)
        a = proj.getAnnotation()
        self.assertIsInstance(a._obj, omero.model.FileAnnotation)
        self.assertEqual(unwrap(a.getFile().getId()), fid)

        tc.close()
        self.delete('/Project', pid)

    def test_getAttachedTableFile(self):
        pid = self.create_project('addFileAnnotationTo')
        p = self.conn.getObject('Project', pid)
        tc = self.Tc(self.conn)
        fid = unwrap(tc.table.getOriginalFile().getId())

        self.assertIsNone(WndcharmStorage.getAttachedTableFile(tc, p))

        WndcharmStorage.addFileAnnotationTo(tc, p)
        self.assertIsNotNone(WndcharmStorage.getAttachedTableFile(tc, p))

        tc.close()
        self.delete('/Project', pid)

    def test_addCommentTo(self):
        pid = self.create_project('addCommentTo')
        txt = 'This is a comment'
        WndcharmStorage.addCommentTo(self.conn, txt, 'Project', pid)

        proj = self.conn.getObject('Project', pid)
        a = proj.getAnnotation()
        self.assertIsInstance(a._obj, omero.model.CommentAnnotation)
        self.assertEqual(unwrap(a.getTextValue()), txt)

        self.delete('/Project', pid)

    def test_addTextFileAnnotationTo(self):
        pid = self.create_project('addTextFileAnnotationTo')
        txt = 'This is\nsome text.'
        filename = 'addTextFileAnnotationTo.txt'
        description = 'Description of addTextFileAnnotationTo.txt'
        WndcharmStorage.addTextFileAnnotationTo(
            self.conn, txt, 'Project', pid, filename, description)

        p = self.conn.getObject('Project', pid)
        anns = list(p.listAnnotations())
        self.assertEqual(len(anns), 1)
        a = anns[0]

        self.assertEqual(a.getFileName(), filename)
        self.assertEqual(a.getDescription(), description)
        self.assertEqual(a.getFileSize(), len(txt))
        self.assertEqual(list(a.getFileInChunks())[0], txt)

        self.delete('/Annotation', a.getId())
        self.delete('/Project', pid)

    def test_addTagTo(self):
        pid = self.create_project('addTagTo')
        txt = 'This is a tag'
        tid = self.create_tag(txt)
        tag = omero.model.TagAnnotationI(tid, False)
        WndcharmStorage.addTagTo(self.conn, tag, 'Project', pid)

        proj = self.conn.getObject('Project', pid)
        a = proj.getAnnotation()
        self.assertIsInstance(a._obj, omero.model.TagAnnotation)
        self.assertEqual(unwrap(a.getTextValue()), txt)
        self.assertEqual(unwrap(a.getId()), tid)

        self.delete('/Project', pid)
        # Note this should also delete the tag

    def test_createClassifierTagSet(self):
        classifierName = 'createClassifierTagSet'
        instanceName = str(uuid.uuid1())
        labels = ['A', 'B']
        WndcharmStorage.createClassifierTagSet(
            self.conn, classifierName, instanceName, labels)

        tagset = list(self.conn.getObjects('TagAnnotation', attributes={
                    'textValue': classifierName + '/' + instanceName,
                    'ns': omero.constants.metadata.NSINSIGHTTAGSET}))
        self.assertEqual(len(tagset), 1)
        tagset = tagset[0]

        tags = list(self.conn.getObjects('TagAnnotation', attributes={
                    'ns': classifierName + '/' + instanceName}))
        self.assertEqual(len(tags), 2)
        self.assertEqual(sorted([t.getValue() for t in tags]), labels)

        for t in tags:
            self.assertEqual(t.getParent(), tagset)

        self.delete('/Annotation', [tagset.getId()] + [t.id for t in tags])

    # Also tests attaching the tagset to a project
    def test_getClassifierTagSet(self):
        pid = self.create_project('addTagTo')
        p = self.conn.getObject('Project', pid)

        classifierName = 'getClassifierTagSet'
        instanceName = str(uuid.uuid1())
        labels = ['A', 'B']
        WndcharmStorage.createClassifierTagSet(
            self.conn, classifierName, instanceName, labels, p)

        tagset = WndcharmStorage.getClassifierTagSet(
            classifierName, instanceName, p)
        self.assertIsNotNone(tagset)
        self.assertEqual(tagset.getNs(),
                         omero.constants.metadata.NSINSIGHTTAGSET)

        tags = list(self.conn.getObjects('TagAnnotation', attributes={
                    'ns': classifierName + '/' + instanceName}))
        self.assertEqual(len(tags), 2)
        self.assertEqual(sorted([t.getValue() for t in tags]), labels)

        for t in tags:
            self.assertEqual(t.getParent(), tagset)

        # Delete the project and tagset but not the child tags
        self.delete('/Project', pid)
        self.delete('/Annotation', [t.id for t in tags])

    def test_deleteTags(self):
        us = self.conn.getUpdateService()

        tagSet = omero.model.TagAnnotationI()
        classifierName = 'getClassifierTagSet'
        instanceName = str(uuid.uuid1())
        instanceNs = classifierName + '/' + instanceName

        tagSet.setTextValue(wrap(instanceNs));
        tagSet.setNs(wrap(omero.constants.metadata.NSINSIGHTTAGSET));
        tagSet = us.saveAndReturnObject(tagSet);

        tag = omero.model.TagAnnotationI()
        tag.setTextValue(wrap(str(uuid.uuid1())));
        tag.setNs(wrap(instanceNs));
        tag = us.saveAndReturnObject(tag);

        link = omero.model.AnnotationAnnotationLinkI()
        link.setChild(tag)
        link.setParent(tagSet)
        link = us.saveAndReturnObject(link)

        self.assertIsNotNone(self.getObject('TagAnnotation', tagSet.id))
        self.assertIsNotNone(self.getObject('TagAnnotation', tag.id))
        self.assertIsNotNone(self.getObject(
                'AnnotationAnnotationLink', link.id))

        WndcharmStorage.deleteTags(self.conn, tagSet)

        self.assertIsNone(self.getObject('TagAnnotation', tagSet.id))
        self.assertIsNone(self.getObject('TagAnnotation', tag.id))
        self.assertIsNone(self.getObject(
                'AnnotationAnnotationLink', link.id))

    def test_unlinkAnnotations(self):
        us = self.conn.getUpdateService()

        f = omero.model.OriginalFileI()
        f.setName(wrap(str(uuid.uuid1())))
        f.setPath(wrap(str(uuid.uuid1())))
        f = self.sess.getUpdateService().saveAndReturnObject(f)

        tag = omero.model.TagAnnotationI()
        tag.setTextValue(wrap(str(uuid.uuid1())));
        tag = us.saveAndReturnObject(tag);

        link = omero.model.OriginalFileAnnotationLinkI()
        link.setChild(tag)
        link.setParent(f)
        link = us.saveAndReturnObject(link)

        self.assertIsNotNone(self.getObject('TagAnnotation', tag.id))
        self.assertIsNotNone(self.getObject('OriginalFile', f.id))
        self.assertIsNotNone(self.getObject(
                'OriginalFileAnnotationLink', link.id))

        file = self.conn.getObject('OriginalFile', unwrap(f.id))
        WndcharmStorage.unlinkAnnotations(self.conn, file)

        self.assertIsNotNone(self.getObject('TagAnnotation', tag.id))
        self.assertIsNotNone(self.getObject('OriginalFile', file.id))
        self.assertIsNone(self.getObject('OriginalFileAnnotationLink', link.id))

        self.delete('/OriginalFile', unwrap(f.id))
        self.delete('/Annotation', unwrap(tag.id))


    @unittest.skip("TODO: Implement")
    def test_datasetGenerator(self):
        WndcharmStorage.datasetGenerator(conn, dataType, ids)



if __name__ == '__main__':
    unittest.main()

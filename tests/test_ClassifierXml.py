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

import collections
import itertools
import StringIO
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'OmeroWndcharm'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from ClassifierXml import *


class TestReader(unittest.TestCase):

    def setUp(self):
        self.filename = os.path.join(os.path.dirname(__file__), 'sample.xml')

    def getXml(self):
        return Reader(xmlFile=self.filename)

    def test_getNs(self):
        xml = self.getXml()
        self.assertEqual(
            xml.getNs(), 'http://www.openmicroscopy.org/Schemas/OME/2012-06')

    def test_getFeatureSet(self):
        xml = self.getXml()
        fs = xml.getFeatureSet(xml.xml)
        self.assertEqual(len(fs), 1)
        fs = fs[0]

        a = fs.algorithm
        self.assertIsNotNone(a)
        self.assertEqual(a.id, 1234)
        self.assertEqual(sorted(a.parameters.keys()), ['bar', 'foo'])
        self.assertEqual(a.parameters['foo'], '345')
        self.assertEqual(a.parameters['bar'], 'abc')

        self.assertEqual(fs.tableId, 654)

        ims = fs.images
        self.assertEqual(len(ims), 3)
        for (i, im) in itertools.izip([52, 53, 54], ims):
            self.assertEqual(im.id, i)
            self.assertEqual(im.z, 0)
            self.assertEqual(im.c, [0, 1, 2])
            self.assertEqual(im.t, 0)


    def test_getClassifierInstance(self):
        xml = self.getXml()
        ci = xml.getClassifierInstance(xml.xml)
        self.assertEqual(len(ci), 1)
        ci = ci[0]

        a = ci.algorithm
        self.assertIsNotNone(a)
        self.assertEqual(a.id, 534)
        self.assertEqual(a.parameters.keys(), ['threshold'])
        self.assertEqual(a.parameters['threshold'], '0.234')

        self.assertEqual(ci.trainingIds, [4235, 6543])
        self.assertEqual(ci.selectedId, 654)
        self.assertEqual(ci.weightsId, 356)

        ls = ci.labels
        self.assertEqual(sorted(ls.keys()), [0, 1])
        self.assertEqual(ls[0], 'cat')
        self.assertEqual(ls[1], 'dog')


    def test_getClassifierPrediction(self):
        xml = self.getXml()
        cp = xml.getClassifierPrediction(xml.xml)
        self.assertEqual(len(cp), 1)
        cp = cp[0]

        a = cp.algorithm
        self.assertIsNotNone(a)
        self.assertEqual(a.id, 599)
        self.assertEqual(a.parameters.keys(), ['g'])
        self.assertEqual(a.parameters['g'], '9.81')

        ps = cp.predictions
        self.assertEqual(len(ps), 2)
        for (i, p) in itertools.izip([52, 53], ps):
            self.assertEqual(p.id, i)
            self.assertEqual(p.z, 0)
            self.assertEqual(p.c, [0])
            self.assertEqual(p.t, 0)



class TestWriter(unittest.TestCase):

    def setUp(self):
        self.writer = Writer()
        self.writer.useDefaultNsForEverything = True

        self.fsxml = (
            '<FeatureSet>'
            '<Algorithm scriptId="12">'
            '<Parameter name="baz" value="3131" />'
            '</Algorithm>'
            '<FeatureTable originalFileId="264345" />'
            '<Image c="2,4" id="666" t="3" z="1" />'
            '<Image c="0,1" id="7" t="43" z="33" />'
            '</FeatureSet>'
            )

        self.cixml = (
            '<ClassifierInstance>'
            '<Algorithm scriptId="12">'
            '<Parameter name="baz" value="3131" />'
            '</Algorithm>'
            '<TrainingFeatures annotationId="4543" />'
            '<TrainingFeatures annotationId="1423" />'
            '<SelectedFeaturesTable originalFileId="7657777" />'
            '<FeatureWeightsTable originalFileId="2352553" />'
            '<ClassLabel index="0">hamster</ClassLabel>'
            '<ClassLabel index="1">mouse</ClassLabel>'
            '</ClassifierInstance>'
            )

        self.cpxml = (
            '<ClassifierPrediction>'
            '<Algorithm scriptId="12">'
            '<Parameter name="baz" value="3131" />'
            '</Algorithm>'
            '<Prediction c="5" imageId="645354" t="456" z="123">'
            '<Label>mouse</Label>'
            '</Prediction>'
            '<Prediction c="2" imageId="9219" t="111" z="14">'
            '<Label>hamster</Label>'
            '</Prediction>'
            '</ClassifierPrediction>'
            )

        self.startxml = (
            '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n'
            '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2012-06" '
            'xmlns:SA="http://www.openmicroscopy.org/Schemas/SA/2012-06">'
            '<SA:StructuredAnnotations>'
            '<SA:XMLAnnotation ID="Annotation:3" Namespace="openmicroscopy.org/omero/analysis/classifier">'
            '<SA:Value>'
            '<Classifier namespace="http://www.openmicroscopy.org/Schemas/Additions/2011-09">'
            )

        self.endxml = (
            '</Classifier>'
            '</SA:Value>'
            '</SA:XMLAnnotation>'
            '</SA:StructuredAnnotations>'
            '</OME>'
            )

    def createFeatureSet(self):
        return FeatureSet(
            Algorithm(12, { 'baz': 3131}),
            264345,
            [Image(666, 1, [2, 4], 3), Image(7, 33, [0, 1], 43)])

    def createClassifierInstance(self):
        return ClassifierInstance(
            Algorithm(12, { 'baz': 3131}),
            [4543, 1423],
            7657777,
            2352553,
            {0: 'hamster', 1: 'mouse'})

    def createClassifierPrediction(self):
        return ClassifierPrediction(
            Algorithm(12, { 'baz': 3131}),
            [Prediction(645354, 123, [5], 456, 'mouse'),
             Prediction(9219, 14, [2], 111, 'hamster')])


    def test_xmlFileOutput(self):
        root = self.writer.omeXml(self.createFeatureSet(),
                                  self.createClassifierInstance(),
                                  self.createClassifierPrediction(),
                                  'Annotation:3')
        buffer = StringIO.StringIO()
        self.writer.writeOmeXml(buffer, root)
        expected = (self.startxml + self.fsxml + self.cixml + self.cpxml +
                    self.endxml)
        for i in xrange(len(expected)):
            b = buffer.getvalue()[i:i+10]
            e = expected[i:i+10]
            if b[0] != e[0]:
                print 'Difference at [%d] *%s* *%s*' % (i, b, e)
                break

        self.assertEqual(len(buffer.getvalue()), len(expected))
        self.assertEqual(buffer.getvalue(), expected)

    def test_xmlFeatureSet(self):
        fsxml = self.writer.toString(self.writer.xmlFeatureSet(
                self.createFeatureSet()))
        self.assertEqual(fsxml, self.fsxml)

    def test_xmlClassifierInstance(self):
        cixml = self.writer.toString(self.writer.xmlClassifierInstance(
                self.createClassifierInstance()))
        self.assertEqual(cixml, self.cixml)

    def test_xmlClassifierPrediction(self):
        cpxml = self.writer.toString(self.writer.xmlClassifierPrediction(
                self.createClassifierPrediction()))
        self.assertEqual(cpxml, self.cpxml)




if __name__ == '__main__':
    unittest.main()

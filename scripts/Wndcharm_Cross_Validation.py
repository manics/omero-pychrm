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
from omero import scripts
import omero.model
from omero.rtypes import rstring, rlong, unwrap
from datetime import datetime
from math import ceil
from itertools import izip
from StringIO import StringIO

from OmeroWndcharm import WndcharmStorage

from wndcharm.FeatureSet import DiscreteClassificationExperimentResult, \
    DiscreteBatchClassificationResult, FeatureSet_Discrete, \
    FisherFeatureWeights, Signatures

def crossValidate(ftb, project, featureThreshold, imagesOnly, numSplits):

    message = ''
    fullSet = FeatureSet_Discrete()
    fullSet.source_path = project.getName()

    classId = 0
    for ds in project.listChildren():
        message += 'Processing dataset id:%d\n' % ds.getId()
        message += addToFeatureSet(ftb, ds, fullSet, classId, imagesOnly)
        classId += 1

    tmp = fullSet.ContiguousDataMatrix()
    experiment = DiscreteClassificationExperimentResult(training_set=fullSet)

    for i in range(numSplits):
        trainSet, testSet = fullSet.Split()
        trainSet.Normalize()
        testSet.Normalize(trainSet)

        weights = FisherFeatureWeights.NewFromFeatureSet(trainSet)

        nFeatures = ceil(len(weights.names) * featureThreshold)
        message += 'Selecting top %d features\n' % nFeatures
        weights = weights.Threshold(nFeatures)
        trainSet = reduceFeatures(trainSet, weights)

        reducedTestSet = reduceFeatures(testSet, weights)
        reducedTrainSet = reduceFeatures(trainSet, weights)

	batchResult = DiscreteBatchClassificationResult.New(
            reducedTrainSet, reducedTestSet, weights, batch_number=i)
	experiment.individual_results.append(batchResult)

    out = StringIO()
    experiment.Print(output_stream=out)
    experiment.PerSampleStatistics(output_stream=out)

    pid = project.getId()
    WndcharmStorage.addTextFileAnnotationTo(
        ftb.conn, out.getvalue(), 'Project', pid,
        'Wndcharm_Cross_Validation_Results.txt',
        'Wndcharm Cross Validation Results for Project:%d' % pid)

    message += 'Attached cross-validation results\n'
    #return experiment
    return message


def reduceFeatures(fts, weights):
    if fts.source_path is None:
        fts.source_path = ''
    ftsr = fts.FeatureReduce(weights.names)
    return ftsr


def addToFeatureSet(ftb, ds, fts, classId, imagesOnly):
    message = ''

    tid = WndcharmStorage.getAttachedTableFile(ftb.tc, ds)
    if tid:
        if not ftb.openTable(tid):
            return message + '\nERROR: Table not opened'
        version = unwrap(ftb.versiontag.getTextValue())
        message += 'Opened table id:%d version:%s\n' % (tid, version)
    else:
        message += 'ERROR: Table not found for Dataset id:%d' % ds.getId()
        return message

    if imagesOnly:
        for image in ds.listChildren():
            imId = image.getId()
            message += '\tProcessing features for image id:%d\n' % imId

            sig = Signatures()
            (sig.names, sig.values) = ftb.loadFeatures(imId)
            sig.source_file = str(imId)
            sig.version = version
            fts.AddSignature(sig, classId)

    else:
        names, values, ids = ftb.bulkLoadFeatures()
        message += '\tProcessing all features for dataset id:%d\n' % ds.getId()

        for imId, vals in izip(ids, values):
            sig = Signatures()
            sig.names = names
            sig.values = vals
            sig.source_file = str(imId)
            sig.version = version
            fts.AddSignature(sig, classId)

    fts.classnames_list[classId] = ds.getName()
    return message


def runCrossValidate(client, scriptParams):
    message = ''

    # for params with default values, we can get the value directly
    dataType = scriptParams['Data_Type']
    projectId = scriptParams['IDs']
    contextName = scriptParams['Context_Name']
    featureThreshold = scriptParams['Features_threshold'] / 100.0
    numSplits = scriptParams['Number_of_splits']
    imagesOnly = scriptParams['Cross_Reference_Table_Images']

    if len(projectId) != 1:
        raise Exception('A single project must be provided')

    projectId = projectId[0]

    tableNameIn = '/Wndcharm/' + contextName + WndcharmStorage.SMALLFEATURES_TABLE
    message += 'tableNameIn:' + tableNameIn + '\n'

    ftb = WndcharmStorage.FeatureTable(client, tableNameIn)

    try:
        message += 'Running cross-validation\n'
        trainProject = ftb.conn.getObject(dataType, projectId)
        msg = crossValidate(
            ftb, trainProject, featureThreshold, imagesOnly, numSplits)
        message += msg

    except:
        print message
        raise
    finally:
        ftb.close()

    return message


def runScript():
    """
    The main entry point of the script, as called by the client via the scripting service, passing the required parameters. 
    """

    client = scripts.client(
        'Wndcharm_Cross_Validation.py',
        'Run multiple cross-validation iterations',

        scripts.String('Data_Type', optional=False, grouping='1',
                       description='The training source.',
                       values=[rstring('Project')], default='Project'),

        scripts.List(
            'IDs', optional=False, grouping='1',
            description='Project ID').ofType(rlong(0)),

        scripts.String(
            'Context_Name', optional=False, grouping='1',
            description='The name of the classification context.',
            default='Example'),

        scripts.Long(
            'Features_threshold', optional=False, grouping='2',
            description='The proportion of features to keep (%)\n' + \
                '(Should be a Double but doesn\'t seem to work)',
            default=15),

        scripts.Long(
            'Number_of_splits', optional=False, grouping='2',
            description='The number of cross-validation splits',
            default=5),

        scripts.Bool(
            'Cross_Reference_Table_Images', optional=False, grouping='2',
            description='Should the features table be cross-references with the list of images in the dataset?',
            default=True),

        version = '0.0.1',
        authors = ['Simon Li', 'Chris Coletta', 'OME Team'],
        institutions = ['University of Dundee'],
        contact = 'ome-users@lists.openmicroscopy.org.uk',
    )

    try:
        startTime = datetime.now()
        session = client.getSession()
        client.enableKeepAlive(60)
        scriptParams = {}

        # process the list of args above.
        for key in client.getInputKeys():
            if client.getInput(key):
                scriptParams[key] = client.getInput(key, unwrap=True)
        message = str(scriptParams) + '\n'

        # Run the script
        message += runCrossValidate(client, scriptParams) + '\n'

        stopTime = datetime.now()
        message += 'Duration: %s' % str(stopTime - startTime)

        print message
        client.setOutput('Message', rstring(str(message)))

    finally:
        client.closeSession()

if __name__ == '__main__':
    runScript()


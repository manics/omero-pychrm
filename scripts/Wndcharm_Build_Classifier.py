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

from OmeroPychrm import PychrmStorage
import pychrm.FeatureSet





def createWeights(ftb, ctb, project, featureThreshold, imagesOnly):
    # Build the classifier (basically a set of weights)
    message = ''
    trainFts = pychrm.FeatureSet.FeatureSet_Discrete()

    classId = 0
    for ds in project.listChildren():
        message += 'Processing dataset id:%d\n' % ds.getId()
        message += addToFeatureSet(ftb, ds, trainFts, classId, imagesOnly)
        classId += 1

    tmp = trainFts.ContiguousDataMatrix()
    weights = pychrm.FeatureSet.FisherFeatureWeights.NewFromFeatureSet(trainFts)

    if featureThreshold < 1.0:
        nFeatures = ceil(len(weights.names) * featureThreshold)
        message += 'Selecting top %d features\n' % nFeatures
        weights = weights.Threshold(nFeatures)
        trainFts = reduceFeatures(trainFts, weights)

    version = trainFts.feature_vector_version

    # Save the features, weights and classes to tables
    # TODO:Delete existing tables
    #if getProjectTableFile(tcOutF, tcF.tableName, proj):
    ctb.createClassifierTables(weights.names, version)
    message += 'Created classifier tables ids: %d %d %d version:%s\n' % (
        ctb.tcF.tableId, ctb.tcW.tableId, ctb.tcL.tableId, version)

    # We've (ab)used imagenames_list to hold the image ids
    ids = [long(a) for b in trainFts.imagenames_list for a in b]
    classIds = [a for b in [[i] * len(z) for i, z in izip(xrange(
                    len(trainFts.imagenames_list)), trainFts.imagenames_list)]
                for a in b]
    featureMatrix = trainFts.data_matrix
    featureNames = weights.names
    featureWeights = weights.values
    classNames = trainFts.classnames_list

    ctb.saveClassifierTables(ids, classIds, featureMatrix,
                             featureNames, featureWeights, classNames)

    PychrmStorage.addFileAnnotationTo(ctb.tcF, project)
    PychrmStorage.addFileAnnotationTo(ctb.tcW, project)
    PychrmStorage.addFileAnnotationTo(ctb.tcL, project)

    message += 'Saved classifier\n'

    classifierName = PychrmStorage.CLASSIFIER_PYCHRM_NAMESPACE
    ns = PychrmStorage.createClassifierTagSet(
        ctb.tcL.conn, classifierName, project.getName(), classNames, project)
    message += 'Created tagset: %s\n' % ns

    return trainFts, weights, message


def reduceFeatures(fts, weights):
    if fts.source_path is None:
        fts.source_path = ''
    ftsr = fts.FeatureReduce(weights.names)
    return ftsr


def addToFeatureSet(ftb, ds, fts, classId, imagesOnly):
    message = ''

    tid = PychrmStorage.getAttachedTableFile(ftb.tc, ds)
    if tid:
        if not ftb.openTable(tid):
            return message + '\nERROR: Table not opened'
        version = unwrap(ftb.versiontag.getTextValue())
        message += 'Opened table id:%d version:%s\n' % (tid, version)
    else:
        message += 'ERROR: Table not found for Dataset id:%d' % ds.getId()
        return message

    #fts = pychrm.FeatureSet.FeatureSet_Discrete({'num_images': 0})
    if imagesOnly:
        for image in ds.listChildren():
            imId = image.getId()
            message += '\tProcessing features for image id:%d\n' % imId

            sig = pychrm.FeatureSet.Signatures()
            (sig.names, sig.values) = ftb.loadFeatures(imId)
            sig.source_file = str(imId)
            sig.version = version
            fts.AddSignature(sig, classId)

    else:
        names, values, ids = ftb.bulkLoadFeatures()
        message += '\tProcessing all features for dataset id:%d\n' % ds.getId()

        for imId, vals in izip(ids, values):
            sig = pychrm.FeatureSet.Signatures()
            sig.names = names
            sig.values = vals
            sig.source_file = str(imId)
            sig.version = version
            fts.AddSignature(sig, classId)

    fts.classnames_list[classId] = ds.getName()
    return message


def trainClassifier(client, scriptParams):
    message = ''

    # for params with default values, we can get the value directly
    dataType = scriptParams['Data_Type']
    projectId = scriptParams['IDs']
    contextName = scriptParams['Context_Name']
    featureThreshold = scriptParams['Features_threshold'] / 100.0
    imagesOnly = scriptParams['Cross_Reference_Table_Images']

    if len(projectId) != 1:
        raise Exception('A single project must be provided')

    projectId = projectId[0]

    tableNameIn = '/Pychrm/' + contextName + PychrmStorage.SMALLFEATURES_TABLE
    tableNameOutF = '/Pychrm/' + contextName + \
        PychrmStorage.CLASS_FEATURES_TABLE
    tableNameOutW = '/Pychrm/' + contextName + \
        PychrmStorage.CLASS_WEIGHTS_TABLE
    tableNameOutL = '/Pychrm/' + contextName + \
        PychrmStorage.CLASS_LABELS_TABLE
    message += 'tableNameIn:' + tableNameIn + '\n'
    message += 'tableNameOutF:' + tableNameOutF + '\n'
    message += 'tableNameOutW:' + tableNameOutW + '\n'
    message += 'tableNameOutL:' + tableNameOutL + '\n'

    ftb = PychrmStorage.FeatureTable(client, tableNameIn)
    ctb = PychrmStorage.ClassifierTables(
        client, tableNameOutF, tableNameOutW, tableNameOutL)

    try:
        # Training
        message += 'Training classifier\n'
        trainProject = ftb.conn.getObject(dataType, projectId)
        trainFts, weights, msg = createWeights(
            ftb, ctb, trainProject, featureThreshold, imagesOnly)
        message += msg

    except:
        print message
        raise
    finally:
        ftb.close()
        ctb.close()

    return message


def runScript():
    """
    The main entry point of the script, as called by the client via the scripting service, passing the required parameters. 
    """

    client = scripts.client(
        'Pychrm_Build_Classifier.py',
        'Build a classifier from features calculated over two or more ' +
        'datasets in a project, each dataset represents a different class',

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

        scripts.Bool(
            'Cross_Reference_Table_Images', optional=False, grouping='2',
            description='Should the features table be cross-references with the list of images in the dataset?',
            default=True),

        version = '0.0.1',
        authors = ['Simon Li', 'OME Team'],
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
        message += trainClassifier(client, scriptParams) + '\n'

        stopTime = datetime.now()
        message += 'Duration: %s' % str(stopTime - startTime)

        print message
        client.setOutput('Message', rstring(str(message)))

    finally:
        client.closeSession()

if __name__ == '__main__':
    runScript()


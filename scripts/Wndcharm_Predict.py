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
import numpy

from OmeroPychrm import PychrmStorage
import pychrm.FeatureSet



def loadClassifier(ctb, project):
    tidF = PychrmStorage.getAttachedTableFile(ctb.tcF, project)
    tidW = PychrmStorage.getAttachedTableFile(ctb.tcW, project)
    tidL = PychrmStorage.getAttachedTableFile(ctb.tcL, project)

    if tidF is None or tidW is None or tidL is None:
        raise Exception('Incomplete set of classifier tables: %s' %
                        (tidF, tidW, tidL))

    ctb.openTables(tidF, tidW, tidL)
    version = unwrap(ctb.versiontag.getTextValue())

    cls = ctb.loadClassifierTables()
    #ids,trainClassIds,featureMatrix,featureNames,weights,classIds,classNames

    trainFts = pychrm.FeatureSet.FeatureSet_Discrete()

    #if cls['classIds'] != sorted(cls['classIds']):
    if cls['classIds'] != range(len(cls['classIds'])):
        raise Exception('Incorrectly ordered class IDs')
    trainFts.classnames_list = cls['classNames']

    # Objects should be in order of increasing class ID, this makes rebuilding
    # data_list much faster
    nclasses = len(cls['classNames'])
    classCounts = [0] * nclasses
    cprev = -1
    for c in cls['trainClassIds']:
        if c < cprev:
            raise Exception('Incorrectly ordered training class feature data')
        cprev = c
        classCounts[c] += 1
    trainFts.classsizes_list = classCounts

    trainFts.feature_vector_version = version

    classFts = [[] for n in xrange(len(cls['classNames']))]
    p = 0
    for i in xrange(nclasses):
        classFts[i] = numpy.array(cls['featureMatrix'][p:(p + classCounts[i])])
        p += classCounts[i]
    trainFts.data_list = classFts
    trainFts.num_images = sum(classCounts)
    trainFts.num_features = len(cls['featureNames'])
    trainFts.num_classes = nclasses

    trainFts.featurenames_list = cls['featureNames']
    trainFts.imagenames_list = [str(i) for i in cls['ids']]
    tmp = trainFts.ContiguousDataMatrix()

    weights = pychrm.FeatureSet.FisherFeatureWeights(
        data_dict={'names': cls['featureNames'], 'values': cls['weights']})
    return (trainFts, weights)



def predictDataset(ftb, trainFts, predDs, weights):
    message = ''
    predictFts = pychrm.FeatureSet.FeatureSet_Discrete()
    classId = 0
    message += addToFeatureSet(ftb, predDs, predictFts, classId)
    tmp = predictFts.ContiguousDataMatrix()

    predictFts = reduceFeatures(predictFts, weights)

    pred = pychrm.FeatureSet.DiscreteBatchClassificationResult.New(
        trainFts, predictFts, weights)
    return pred, message


def formatPredResult(r):
    return 'ID:%s Prediction:%s Probabilities:[%s]' % \
        (r.source_file, r.predicted_class_name,
         ' '.join(['%.3f' % p for p in r.marginal_probabilities]))


def addPredictionsToImages(conn, prediction, dsId, commentImages, tagSet):
    """
    Add a comment to the dataset containing the prediction results.
    @param commentImages If true add comment to individual images as well
    as the dataset
    @param tagSet If provided then tag images with the predicted label
    """
    message = ''
    dsComment = ''

    tagMap = {}
    if tagSet:
        for tag in tagSet.listTagsInTagset():
            tagMap[tag.getValue()] = tag

    for r in prediction.individual_results:
        c = formatPredResult(r)
        imId = long(r.source_file)

        if commentImages:
            message += PychrmStorage.addCommentTo(conn, c, 'Image', imId)
        im = conn.getObject('Image', imId)
        dsComment += im.getName() + ' ' + c + '\n'

        if tagMap:
            tag = tagMap[r.predicted_class_name]._obj
            message += PychrmStorage.addTagTo(conn, tag, 'Image', imId)

    message += PychrmStorage.addCommentTo(conn, dsComment, 'Dataset', dsId)
    return message


def reduceFeatures(fts, weights):
    if fts.source_path is None:
        fts.source_path = ''
    ftsr = fts.FeatureReduce(weights.names)
    return ftsr


def addToFeatureSet(ftb, ds, fts, classId):
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
    for image in ds.listChildren():
        imId = image.getId()
        message += '\tProcessing features for image id:%d\n' % imId
        #message += extractFeatures(tc, d, im = image) + '\n'
        sig = pychrm.FeatureSet.Signatures()
        (sig.names, sig.values) = ftb.loadFeatures(imId)
        #sig.source_file = image.getName()
        sig.source_file = str(imId)
        sig.version = version
        fts.AddSignature(sig, classId)

    fts.classnames_list[classId] = ds.getName()
    return message


def predict(client, scriptParams):
    message = ''

    # for params with default values, we can get the value directly
    projectId = scriptParams['Training_Project_ID']
    dataType = scriptParams['Data_Type']
    predictIds = scriptParams['IDs']
    commentImages = scriptParams['Comment_Images']
    tagImages = scriptParams['Tag_Images']

    contextName = scriptParams['Context_Name']

    tableNameIn = '/Pychrm/' + contextName + PychrmStorage.SMALLFEATURES_TABLE
    tableNameF = '/Pychrm/' + contextName + \
        PychrmStorage.CLASS_FEATURES_TABLE
    tableNameW = '/Pychrm/' + contextName + \
        PychrmStorage.CLASS_WEIGHTS_TABLE
    tableNameL = '/Pychrm/' + contextName + \
        PychrmStorage.CLASS_LABELS_TABLE
    message += 'tableNameIn:' + tableNameIn + '\n'
    message += 'tableNameF:' + tableNameF + '\n'
    message += 'tableNameW:' + tableNameW + '\n'
    message += 'tableNameL:' + tableNameL + '\n'

    ftb = PychrmStorage.FeatureTable(client, tableNameIn)
    ctb = PychrmStorage.ClassifierTables(
        client, tableNameF, tableNameW, tableNameL)

    try:
        message += 'Loading classifier\n'
        trainProject = ftb.conn.getObject('Project', projectId)
        trainFts, weights = loadClassifier(ctb, trainProject)
        classifierName = PychrmStorage.CLASSIFIER_PYCHRM_NAMESPACE
        tagSet = PychrmStorage.getClassifierTagSet(
            classifierName, trainProject.getName(), trainProject)

        # Predict
        message += 'Predicting\n'
        predDatasets = PychrmStorage.datasetGenerator(
            ftb.conn, dataType, predictIds)

        for ds in predDatasets:
            message += 'Predicting dataset id:%d\n' % ds.getId()
            pred, msg = predictDataset(ftb, trainFts, ds, weights)
            message += msg
            message += addPredictionsToImages(ftb.conn, pred, ds.getId(),
                                              commentImages, tagSet)

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
        'Pychrm_Predict.py',
        'Tag images based on their classification result',

        scripts.String('Data_Type', optional=False, grouping='1',
                       description='The source data to be predicted.',
                       values=[rstring('Project'), rstring('Dataset')], default='Dataset'),

        scripts.List(
            'IDs', optional=False, grouping='1',
            description='List of Dataset IDs to be predicted').ofType(rlong(0)),

        scripts.Long(
            'Training_Project_ID', optional=False, grouping='2',
            description='Project ID used for training'),

        scripts.Bool(
            'Comment_Images', optional=False, grouping='3',
            description='Add predictions as image comments', default=True),

        scripts.Bool(
            'Tag_Images', optional=False, grouping='4',
            description='Tag images with predictions', default=True),

        scripts.String(
            'Context_Name', optional=False, grouping='5',
            description='The name of the classification context.',
            default='Example'),

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
        message += predict(client, scriptParams) + '\n'

        stopTime = datetime.now()
        message += 'Duration: %s' % str(stopTime - startTime)

        print message
        client.setOutput('Message', rstring(str(message)))

    finally:
        client.closeSession()

if __name__ == '__main__':
    runScript()


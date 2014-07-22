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
from omero.util import script_utils
import omero.model
from omero.rtypes import rstring, rlong, unwrap
from datetime import datetime
from itertools import izip
from tempfile import NamedTemporaryFile


import pychrm
from pychrm.FeatureSet import Signatures
from pychrm.PyImageMatrix import PyImageMatrix
from OmeroPychrm import PychrmStorage

try:
    from PIL import Image, ImageDraw, ImageFont     # see ticket:2597
except: #pragma: nocover
    try:
        import Image, ImageDraw, ImageFont          # see ticket:2597
    except:
        raise omero.ServerError('No PIL installed')


def extractFeatures(ftb, ds, newOnly, chNames, imageId = None, im = None):
    message = ''
    tc = ftb.tc

    # dataset must be explicitly provided because an image can be linked to
    # multiple datasets in which case im.getDataset() doesn't work
    if not im:
        if not imageId:
            #raise Exception('No input image')
            raise omero.ServerError('No input image')

        im = ftb.conn.getObject('Image', imageId)
        if not im:
            return 'Image id:%d not found\n' % imageId
    else:
        imageId = im.getId()

    tid = PychrmStorage.getAttachedTableFile(ftb.tc, ds)
    if tid:
        if not ftb.openTable(tid):
            return message + '\nERROR: Table not opened\n'
        version = unwrap(ftb.versiontag.getTextValue())
        # version seems to be in unicode
        message += 'Opened table id:%d version:%s\n' % (tid, str(version))

        if newOnly and ftb.tableContainsId(imageId):
            return message + 'Image id:%d features already in table' % imageId

    # FIXME: default is convert multichannel to greyscale unless user input

    # Calculate features for an image channel
    # Optionally prepend the channel label to each feature name and combine
    ftall = None
    for c in xrange( len( chNames ) ):
	    
        pychrm_matrix = PyImageMatrix()
        pychrm_matrix.allocate( im.getSizeX(), im.getSizeY() )
        numpy_matrix = pychrm_matrix.as_ndarray()

        numpy_matrix[:] = im.getPrimaryPixels().getPlane(theZ=0,theC=c,theT=0)
        feature_plan = pychrm.StdFeatureComputationPlans.getFeatureSet();
        options = "" # This is where you can tell wnd-charm to normalize pixel intensities, 
                     # take ROIs etc. ... leave blank for now.
        ft = Signatures.NewFromFeatureComputationPlan( pychrm_matrix, feature_plan, options )  

        ft.names = [PychrmStorage.insert_channel_name(
                    n, chNames[c]) for n in ft.names]
        ft.source_path = im.getName()
        if not ftall:
            ftall = ft
        else:
            ftall.names += ft.names
            ftall.values += ft.values

    # Save the features to a table
    if not tid:
        ftb.createTable(ftall.names, ft.version)
        version = unwrap(ftb.versiontag.getTextValue())
        message += 'Created new table id:%d version:%s\n' % (
            ftb.tc.tableId, version)
        message += PychrmStorage.addFileAnnotationTo(tc, ds)

    if version != ft.version:
        return message + 'Incompatible version: Stored=%s Calculated=%s' % (
            version, ft.version)
    ftb.saveFeatures(imageId, ftall)

    return message + 'Extracted features from Image id:%d\n' % imageId


def checkChannels(datasets):
    message = ''
    channels = None
    imref = None
    good = False

    for d in datasets:
        message += 'Checking channels in dataset id:%d\n' % d.getId()
        for image in d.listChildren():
            ch = [c.getLabel() for c in image.getChannels()]
            if imref is None:
                channels = ch
                imref = image.getId()
                message += 'Got channels %s, image id:%d\n' % (channels, imref)
                good = True
            elif channels != ch:
                message += 'Expected channels %s, image id:%d has %s\n' % \
                    (channels, image.getId(), ch)
                good = False

    return good, channels, message


def processImages(client, scriptParams):
    message = ''

    # for params with default values, we can get the value directly
    dataType = scriptParams['Data_Type']
    ids = scriptParams['IDs']
    contextName = scriptParams['Context_Name']
    newOnly = scriptParams['New_Images_Only']

    tableName = '/Pychrm/' + contextName + '/SmallFeatureSet.h5'
    message += 'tableName:' + tableName + '\n'
    ftb = PychrmStorage.FeatureTable(client, tableName)

    try:
        nimages = 0

        # Get the datasets
        objects, logMessage = script_utils.getObjects(ftb.conn, scriptParams)
        message += logMessage

        if not objects:
            return message

        datasets = list(PychrmStorage.datasetGenerator(
                ftb.conn, dataType, ids))

        good, chNames, msg = checkChannels(datasets)
        message += msg
        if not good:
            raise omero.ServerError(
                'Channel check failed, ' +
                'all images must have the same channels: %s' % message)

        for d in datasets:
            message += 'Processing dataset id:%d\n' % d.getId()
            for image in d.listChildren():
                message += 'Processing image id:%d\n' % image.getId()
                msg = extractFeatures(ftb, d, newOnly, chNames, im=image)
                message += msg + '\n'

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
        'Pychrm_Feature_Extraction_Multichannel.py',
        'Extract the small Pychrm feature set from images',

        scripts.String('Data_Type', optional=False, grouping='1',
                       description='The data you want to work with.',
                       values=[rstring('Project'), rstring('Dataset')],
                       default='Dataset'),

        scripts.List(
            'IDs', optional=False, grouping='1',
            description='List of Dataset IDs or Image IDs').ofType(rlong(0)),

        scripts.String(
            'Context_Name', optional=False, grouping='2',
            description='The name of the classification context.',
            default='Example'),

        scripts.Bool(
            'New_Images_Only', optional=False, grouping='3',
            description='If features already exist for an image do not recalculate.',
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
        message += processImages(client, scriptParams) + '\n'

        stopTime = datetime.now()
        message += 'Duration: %s' % str(stopTime - startTime)

        print message
        client.setOutput('Message', rstring(str(message)))

    finally:
        client.closeSession()

if __name__ == '__main__':
    runScript()


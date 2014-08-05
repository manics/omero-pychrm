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
from omero.rtypes import rstring, rlong
from datetime import datetime


from OmeroWndcharm import WndcharmStorage



def countCompleted(ftb, ds):
    message = ''
    tc = ftb.tc

    imIds = [im.getId() for im in ds.listChildren()]
    tid = WndcharmStorage.getAttachedTableFile(ftb.tc, ds)
    if tid is None:
        message += 'Image feature status PRESENT:%d ABSENT:%d\n' % \
            (0, len(imIds))
        return message

    if not ftb.openTable(tid):
        message += 'ERROR: Table not opened\n'
        message += 'Image feature status UNKNOWN:%d\n' % len(imIds)
        return message

    message += 'Opened table id:%d\n' % tid
    d = tc.chunkedRead([0], 0, tc.table.getNumberOfRows(), 100)
    ftImIds = d.columns[0].values
    matchedIds = set(imIds).intersection(ftImIds)
    message += 'Image feature status PRESENT:%d ABSENT:%d\n' % \
        (len(matchedIds), len(imIds) - len(matchedIds))
    return message


def processImages(client, scriptParams):
    message = ''

    # for params with default values, we can get the value directly
    dataType = scriptParams['Data_Type']
    ids = scriptParams['IDs']
    contextName = scriptParams['Context_Name']

    tableName = '/Wndcharm/' + contextName + '/SmallFeatureSet.h5'
    message += 'tableName:' + tableName + '\n'
    ftb = WndcharmStorage.FeatureTable(client, tableName)

    try:
        # Get the datasets
        objects, logMessage = script_utils.getObjects(ftb.conn, scriptParams)
        message += logMessage

        if not objects:
            return message

        datasets = WndcharmStorage.datasetGenerator(ftb.conn, dataType, ids)
        for ds in datasets:
            message += 'Processing dataset id:%d\n' % ds.getId()
            msg = countCompleted(ftb, ds)
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
        'Wndcharm_Feature_Check_Progress.py',
        'Extract the small Wndcharm feature set from images',

        scripts.String('Data_Type', optional=False, grouping='1',
                       description='The data you want to work with.',
                       values=[rstring('Project'), rstring('Dataset')],
                       default='Dataset'),

        scripts.List(
            'IDs', optional=False, grouping='1',
            description='List of Dataset IDs or Image IDs').ofType(rlong(0)),

        scripts.String(
            'Context_Name', optional=False, grouping='1',
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
        message += processImages(client, scriptParams) + '\n'

        stopTime = datetime.now()
        message += 'Duration: %s' % str(stopTime - startTime)

        print message
        client.setOutput('Message', rstring(str(message)))

    finally:
        client.closeSession()

if __name__ == '__main__':
    runScript()


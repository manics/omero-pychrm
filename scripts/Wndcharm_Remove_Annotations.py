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
from omero.rtypes import rstring, rlong, wrap, unwrap
from omero.gateway import BlitzGateway
from omero.gateway import FileAnnotationWrapper, CommentAnnotationWrapper
import omero
from datetime import datetime

from OmeroPychrm import PychrmStorage


def deleteObjects(conn, objType, ids):
    if ids:
        handle = conn.deleteObjects(objType, ids)
        try:
            conn._waitOnCmd(handle, len(ids))
        finally:
            handle.close()

def removeAnnotations(conn, obj, rmTables, rmComments, unlinkTags, rmTagsets):
    """
    Remove annotations that are in one of the PyChrm namespaces
    """
    message = ''

    rmIds = []
    for ann in obj.listAnnotations():
        if ann.getNs() == PychrmStorage.PYCHRM_NAMESPACE:
            if rmTables and isinstance(ann, FileAnnotationWrapper):
                # Need to remove version annotation on the OriginalFile
                # otherwise delete will fail
                PychrmStorage.unlinkAnnotations(conn, ann.getFile())
                message += ('Checking for annotations on file id:%d\n' %
                            ann.getFile().getId())
                rmIds.append(ann.getId())

            if rmComments and isinstance(ann, CommentAnnotationWrapper):
                rmIds.append(ann.getId())

    deleteObjects(conn, 'Annotation', rmIds)

    message += 'Removed annotations:%s from %s id:%d\n' % \
        (rmIds, obj.OMERO_CLASS, obj.getId())

    if unlinkTags:
        message += removeTagAnnotations(conn, obj)

    if rmTagsets:
        message += removeTags(conn, obj)

    try:
        # Keep recursing until listChildren not implemented
        for ch in obj.listChildren():
            message += removeAnnotations(
                conn, ch, rmTables, rmComments, unlinkTags, rmTagsets)
    except NotImplementedError:
        pass

    return message


def removeTagAnnotations(conn, obj):
    """
    Unlink tag annotations, but do not delete the tags
    """
    linkType = obj.OMERO_CLASS + 'AnnotationLink'
    q = 'select oal from %s as oal join ' \
        'fetch oal.child as ann where oal.parent.id = :parentid and ' \
        'oal.child.ns like :ns' % linkType
    params = omero.sys.Parameters()
    params.map = {
        'parentid': wrap(obj.getId()),
        'ns': wrap(PychrmStorage.CLASSIFIER_PYCHRM_NAMESPACE + '/%')
        }
    anns = conn.getQueryService().findAllByQuery(q, params)

    rmIds = []
    rmTags = []
    for ann in anns:
        if isinstance(ann.child, omero.model.TagAnnotation):
            rmIds.append(unwrap(ann.getId()))
            rmTags.append(unwrap(ann.child.getTextValue()))

    deleteObjects(conn, linkType, rmIds)

    message = 'Removed tags: %s from %s id:%d\n' % (
        rmTags, obj.OMERO_CLASS, obj.getId())
    return message


def removeTags(conn, obj):
    """
    Delete classifier tagsets attached to a project

    Note it is not possible to set a namespace for tagsets, so we rely on the
    tag value beginning with PychrmStorage.CLASSIFIER_PYCHRM_NAMESPACE
    """
    if obj.OMERO_CLASS != 'Project':
        return ''

    q = 'select oal from ProjectAnnotationLink as oal join ' \
        'fetch oal.child as ann where oal.parent.id = :parentid and ' \
        'oal.child.ns = :ns and ' \
        'oal.child.textValue like :value'
    params = omero.sys.ParametersI()
    params.addLong('parentid', obj.getId())
    params.addString('ns', omero.constants.metadata.NSINSIGHTTAGSET)
    params.addString('value', PychrmStorage.CLASSIFIER_PYCHRM_NAMESPACE + '/%')
    anns = conn.getQueryService().findAllByQuery(q, params)

    rmTagsets = [unwrap(ann.getChild().getId()) for ann in anns]

    if rmTagsets:
        q = 'select oal from AnnotationAnnotationLink as oal join ' \
            'fetch oal.child join fetch oal.parent '\
            'where oal.parent.id in (:parentids) and ' \
            'oal.child.ns like :ns'
        params = omero.sys.ParametersI()
        params.addLongs('parentids', rmTagsets)
        params.addString('ns', PychrmStorage.CLASSIFIER_PYCHRM_NAMESPACE + '/%')
        anns = conn.getQueryService().findAllByQuery(q, params)

        rmTags = [unwrap(ann.getChild().getId()) for ann in anns]
    else:
        rmTags = []

    deleteObjects(conn, 'Annotation', rmTagsets + rmTags)

    message = 'Removed tagsets: %s tags: %s from %s id:%d\n' % (
        rmTagsets, rmTags, obj.OMERO_CLASS, obj.getId())
    return message


def processObjects(client, scriptParams):
    message = ''

    # for params with default values, we can get the value directly
    dataType = scriptParams['Data_Type']
    ids = scriptParams['IDs']
    rmTables = scriptParams['Remove_tables']
    rmComments = scriptParams['Remove_comments']
    unlinkTags = scriptParams['Untag_images']
    rmTagsets = scriptParams['Remove_tagsets']

    # Get the images or datasets
    conn = BlitzGateway(client_obj=client)
    objects, logMessage = script_utils.getObjects(conn, scriptParams)
    message += logMessage
    if not objects:
        return None, message

    for o in objects:
        message += removeAnnotations(
            conn, o, rmTables, rmComments, unlinkTags, rmTagsets)

    return message


def runScript():
    """
    The main entry point of the script, as called by the client via the scripting service, passing the required parameters.
    """

    dataTypes = [rstring('Project'), rstring('Dataset'), rstring('Image')]
    client = scripts.client(
        'Pychrm_Remove_Annotations.py',
        'Remove Pychrm annotations from Datasets and contained Images, or just Images',

        scripts.String('Data_Type', optional=False, grouping='1',
                       description='The data you want to work with.',
                       values=dataTypes, default='Image'),

        scripts.List(
            'IDs', optional=False, grouping='1',
            description='List of Dataset IDs or Image IDs').ofType(rlong(0)),

        scripts.Bool(
            'Remove_tables', optional=False, grouping='2',
            description='Remove table (HDF5 file) annotations', default=False),

        scripts.Bool(
            'Remove_comments', optional=False, grouping='3',
            description='Remove comments', default=True),

        scripts.Bool(
            'Untag_images', optional=False, grouping='4',
            description='Remove tags from images', default=True),

        scripts.Bool(
            'Remove_tagsets', optional=False, grouping='5',
            description='Remove classifier tagsets and tags', default=False),

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
        message += processObjects(client, scriptParams) + '\n'

        stopTime = datetime.now()
        message += 'Duration: %s' % str(stopTime - startTime)

        print message
        client.setOutput('Message', rstring(str(message)))

    finally:
        client.closeSession()

if __name__ == '__main__':
    runScript()

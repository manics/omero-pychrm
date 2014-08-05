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
from itertools import izip
import logging
import omero
from copy import deepcopy
from omero.gateway import BlitzGateway
from omero.grid import LongColumn, BoolColumn, \
    LongArrayColumn, DoubleArrayColumn

# Retry openTable and newTable, see trac #10464
TABLE_RETRIES = 5

class TableConnectionError(Exception):
    """
    Errors occuring in the TableConnection class
    """
    pass


class Connection(object):
    """
    A wrapper for managing a client session context
    """

    def __init__(self, user = None, passwd = None, host = None, client = None):
        """
        Create a new client session, either by specifying user and passwd or by
        providing a client object (for scripts)
        @param user Username
        @param passwd Password
        @param host The server hostname
        @param client Client object with an active session
        """

        self.log = logging.getLogger(__name__)
        #self.log.setLevel(logging.DEBUG)

        if not client:
            client = omero.client(host)
            sess = client.createSession(user, passwd)
            client.enableKeepAlive(60)
        else:
            sess = client.getSession()

        self.conn = BlitzGateway(client_obj = client)

        self.res = sess.sharedResources()
        if (not self.res.areTablesEnabled()):
            raise TableConnectionError('OMERO.tables not enabled')

    def __enter__(self):
        self.log.debug('Entering Connection')
        return self

    def __exit__(self, type, value, traceback):
        self.log.debug('Exiting Connection')
        self.close()

    def close(self):
        """
        Child classes can override this method but must explcitly call this
        method to ensure the client session is cleaned
        """
        self.log.debug('Closing Connection')
        self.conn._closeSession()


class TableConnection(Connection):
    """
    A basic client-side wrapper for OMERO.tables which handles opening
    and closing tables.
    """

    def __init__(self, user = None, passwd = None, host = None, client = None,
                 tableName = None):
        """
        Create a new table handler, either by specifying user and passwd or by
        providing a client object (for scripts)
        @param user Username
        @param passwd Password
        @param host The server hostname
        @param client Client object with an active session
        @param tableName If provided the name of any table opened by subsequent
        calls will be checked against this, and any new tables will be named
        by this
        """
        super(TableConnection, self).__init__(user, passwd, host, client)

        repos = self.res.repositories()
        self.rid = repos.descriptions[0].id.val

        self.tableName = tableName
        self.tableId = None
        self.table = None

    def close(self, parent=True):
        """
        Close all tables.
        @param parent if True then also call the parent class close() method
        """
        self.log.debug('Closing TableConnection')
        try:
            self.closeTable()
            self.tableId = None
            self.table = None
        finally:
            if parent:
                super(TableConnection, self).close()


    def openTable(self, tableId):
        """
        Opens an existing table by ID.
        @param tableId The OriginalFile ID of the table file, required.
        @return handle to the table
        """

        def openRetry(ofile, n):
            """
            OMERO openTable sometimes returns None for no apparent reason, even
            though the underlying getTable() call works.
            Automatically retry opening the table n times.
            Throws an exception if the table has still not been opened.
            See trac #10464
            """
            for i in xrange(n):
                t = self.res.openTable(ofile)
                if t:
                    return t
                self.log.error('Failed to open table %d (attempt %d)',
                               ofile.getId().val, i + 1)
            raise TableConnectionError(
                'Failed to open table %d' % ofile.getId().val)


        if not tableId:
            tableId = self.tableId
        if not tableId:
            raise TableConnectionError('Table ID required')

        attrs = {'id': long(tableId)}
        ofile = self.conn.getObject("OriginalFile", attributes = attrs)
        if not ofile:
            raise TableConnectionError('No table found with id:%s' % tableId)
        if self.tableName and ofile.getName() != self.tableName:
            raise TableConnectionError(
                'Expected table id:%s to have name:%s, instead found %s' % (
                    tableId, self.tableName, ofile.getName()))

        if self.tableId == ofile.getId():
            if not self.table:
                self.log.warn('Expected table to be already open')
        else:
            self.table = None

        if self.table:
            self.log.debug('Using existing connection to table id:%d', tableId)
        else:
            self.closeTable()
            self.table = openRetry(ofile._obj, TABLE_RETRIES)
            self.tableId = ofile.getId()
            self.log.debug('Opened table id:%d', self.tableId)

        try:
            self.log.debug('\t%d rows %d columns', self.table.getNumberOfRows(),
                           len(self.table.getHeaders()))
        except omero.ApiUsageException:
            pass

        return self.table


    def findByName(self):
        """
        Searches for OriginalFile objects by name, does not check whether
        file is a table
        @return an iterator to a sequence of OriginalFiles
        """
        if not self.tableName:
            raise TableConnectionError('No tableName set')
        attrs = {'name': self.tableName}
        return self.conn.getObjects("OriginalFile", attributes = attrs)


    def deleteAllTables(self):
        """
        Delete all tables with tableName
        Will fail if there are any annotation links
        """
        if not self.tableName:
            raise TableConnectionError('No tableName set')
        ofiles = self.conn.getObjects("OriginalFile", \
            attributes = {'name': self.tableName})
        ids = [f.getId() for f in ofiles]
        self.log.debug('Deleting ids:%s', ids)
        self.conn.deleteObjects('OriginalFile', ids)


    def closeTable(self):
        """
        Close the table if open, and set table and tableId to None
        """
        try:
            if self.table:
                self.table.close()
        finally:
            self.table = None
            self.tableId = None


    def newTable(self, schema):
        """
        Create a new uninitialised table
        @param schema the table description
        @return A handle to the table
        """
        def newRetry(rid, name, n):
            """
            OMERO newTable sometimes returns None for no apparent reason
            Automatically retry n times.
            See trac #10464
            """
            for i in xrange(n):
                t = self.res.newTable(rid, name)
                if t:
                    return t
                self.log.error('Failed to create new table %s (attempt %d)',
                               name, i + 1)
            raise TableConnectionError(
                'Failed to create new table %s' % name)


        self.closeTable()
        if not self.tableName:
            raise TableConnectionError('No tableName set')

        self.table = newRetry(self.rid, self.tableName, TABLE_RETRIES)
        ofile = self.table.getOriginalFile()
        self.tableId = ofile.getId().getValue()

        try:
            self.table.initialize(schema)
            self.log.debug("Initialised '%s' (%d)",
                           self.tableName, self.tableId)
        except Exception as e:
            self.log.error("Failed to create table: %s", e)
            try:
                self.table.delete()
            except Exception as ed:
                self.log.error("Failed to delete table: %s", ed)

            self.table = None
            self.tableId = None
            raise e

        return self.table


    def getHeaders(self):
        """
        Get a set of empty columns corresponding to the table schema
        @return a set of empty table columns
        """
        return self.table.getHeaders()


    def getNumberOfRows(self):
        """
        Get the number of rows
        @return the number of rows in the table
        """
        return self.table.getNumberOfRows()


    def chunkedRead(self, colNumbers, start, stop, chunk):
        """
        Split a call to table.read(), into multiple chunks to limit the number
        of rows returned in one go.
        @param colNumbers A list of columns indices to be read
        @param start The first row to be read
        @param stop The last + 1 row to be read
        @param chunk The maximum number of rows to read in each call
        @return a data object, note lastModified will be set to the timestamp
        the first chunked call
        """
        p = start
        q = min(start + chunk, stop)
        data = self.table.read(colNumbers, p, q)
        p, q = q, min(q + chunk, stop)

        while p < stop:
            data2 = self.table.read(colNumbers, p, q)
            data.rowNumbers.extend(data2.rowNumbers)
            for (c, c2) in izip(data.columns, data2.columns):
                c.values.extend(c2.values)
            p, q = q, min(q + chunk, stop)

        return data


    def chunkedAddData(self, columns, chunk):
        """
        Split a call to table.addData(), into multiple chunks to limit the
        number of rows added in one go.
        @param columns A full list of columns holding data to be added
        @param chunk The maximum number of rows to write in each call
        @return the number of rows written
        """
        nv = [len(c.values) for c in columns]
        if len(set(nv)) != 1:
            raise TableConnectionError(
                'All columns must be the same length, received: %s' % nv)
        nv = nv[0]

        headers = self.table.getHeaders()
        if len(columns) != len(headers) or \
                [h.name for h in headers] != [c.name for c in columns] or \
                [type(h) for h in headers] != [type(c) for c in columns]:
            raise TableConnectionError(
                'Mismatch between columns and table headers')

        p = 0
        q = 0
        p, q = q, min(q + chunk, nv)

        while p < nv:
            for (h, c) in izip(headers, columns):
                h.values = c.values[p:q]
            self.table.addData(headers)
            p, q = q, min(q + chunk, nv)

        return p



class FeatureTableConnection(TableConnection):
    """
    A client side wrapper for OMERO.tables which simulates the effect of
    optional array-columns.
    Also allow within-array selections.

    Internally this uses an addition set of BoolColumns to indicate whether
    a column contains valid data (True) or is null (False)

    @todo Cache some of the metadata (e.g. column names) instead of
    requesting every time
    """

    def __init__(self, user = None, passwd = None, host = None, client = None,
                 tableName = None):
        """
        Just calls the base-class constructor
        """
        super(FeatureTableConnection, self).__init__(user, passwd, host, client,
                                                     tableName)

    def createNewTable(self, idcolName, colDescriptions):
        """
        Create a new table with an id LongColumn followed by
        a set of nullable DoubleArrayColumns
        @param idcolName The name of the id LongColumn
        @param colDescriptions A list of 2-tuples describing each column in
        the form [(name, size), ...]
        """

        # Create an identical number of bool columns indicating whether
        # columns are valid or not. To make things easier this includes
        # a bool column for the id column even though it should always
        # be valid.

        cols = [LongColumn(idcolName)] + \
            [DoubleArrayColumn(name, '', size) \
                 for (name, size) in colDescriptions] + \
                 [BoolColumn('_b_' + idcolName)] + \
                 [BoolColumn('_b_' + name) \
                      for (name, size) in colDescriptions]
        self.newTable(cols)


    def isValid(self, colNumbers, start, stop):
        """
        Check whether the requested arrays are valid
        @param colNumbers Column numbers
        @param start The first row to be read
        @param stop The last + 1 row to be read
        @return A list of BoolColumns indicating whether the corresponding
        row-column element is valid (True) or null (False).
        """
        nCols = self._checkColNumbers(colNumbers)
        bcolNumbers = map(lambda x: x + nCols, colNumbers)
        data = self.table.read(bcolNumbers, start, stop)
        return data.columns


    def readSubArray(self, colArrayNumbers, start, stop):
        """
        Read the requested array columns and indices from the table
        @param colArrayNumbers A dictionary mapping column numbers to
        an array of subindices e.g. {1:[1,3], 3:[0]}
        @param start The first row to be read
        @param stop The last + 1 row to be read
        @return A list of columns with the requested array elements, which
        may be empty (null). If the id column is requested this will not be
        an array. Columns are returned in the order given by
        colArrayNumbers.keys()
        """

        colNumbers = colArrayNumbers.keys()
        subIndices = colArrayNumbers.values()
        nCols = self._checkColNumbers(colNumbers)
        nWanted = len(colNumbers)

        bcolNumbers = map(lambda x: x + nCols, colNumbers)
        data = self.table.read(colNumbers + bcolNumbers, start, stop)
        columns = data.columns

        for (c, b, s) in izip(columns[:nWanted], columns[nWanted:], subIndices):
            #indexer = opertor.itemgetter(*s)
            if isinstance(c, (LongArrayColumn, DoubleArrayColumn)):
                c.values = [[x[i] for i in s] if y else []
                            for (x, y) in izip(c.values, b.values)]
            else:
                self._nullEmptyColumns(c, b)

        return columns[:nWanted]


    def readArray(self, colNumbers, start, stop, chunk=None):
        """
        Read the requested array columns which may include null entries
        @param colNumbers Column numbers
        @param start The first row to be read
        @param stop The last + 1 row to be read
        @param chunk The number of rows to be read in each request, default all
        @return a list of columns
        """

        nCols = self._checkColNumbers(colNumbers)
        nWanted = len(colNumbers)

        bcolNumbers = map(lambda x: x + nCols, colNumbers)
        if chunk:
            data = self.chunkedRead(colNumbers + bcolNumbers, start, stop,
                                    chunk)
        else:
            data = self.table.read(colNumbers + bcolNumbers, start, stop)
        columns = data.columns

        for (c, b) in izip(columns[:nWanted], columns[nWanted:]):
            self._nullEmptyColumns(c, b)

        return columns[:nWanted]


    def getRowId(self, id):
        """
        Find the row index corresponding to a particular id in the first column
        @param id the id of the object to be retrieved
        @return the row index of the object, if the object is present in
        multiple rows returns the highest row index, or None if not found
        """
        columns = self.table.getHeaders()
        nrows = self.getNumberOfRows()
        condition = '(%s==%d)' % (columns[0].name, id)
        idx = self.table.getWhereList(condition=condition, variables={},
                                      start=0, stop=nrows, step=0)

        if not idx:
            return None
        if len(idx) > 1:
            self.log.warn("Multiple rows found, returning last")
            # Ordering of rows not guaranteed
        return max(idx)


    def getHeaders(self):
        """
        Get a set of columns to be used for populating the table with data
        @return a list of empty columns
        """
        columns = self.table.getHeaders()
        return columns[:(len(columns) / 2)]


    def addData(self, cols, copy=True):
        """
        Add a new row of data where DoubleArrays may be null
        @param cols A list of columns obtained from getHeaders() whose values
        have been filled with the data to be added.
        """
        columns = self.table.getHeaders()
        nCols = len(columns) / 2
        if len(cols) != nCols:
            raise TableConnectionError(
                "Expected %d columns, got %d" % (nCols, len(cols)))

        if not isinstance(cols[0], LongColumn) or not \
                all(map(lambda x: isinstance(x, DoubleArrayColumn), cols[1:])):
            raise TableConnectionError(
                "Expected 1 LongColumn and %d DoubleArrayColumn" % (nCols - 1))

        if copy:
            columns[:nCols] = deepcopy(cols)
        else:
            columns[:nCols] = cols

        # Handle first ID column separately, it is not a DoubleArray
        columns[nCols].values = [True] * len(cols[0].values)
        for (c, b) in izip(columns[1:nCols], columns[(nCols + 1):]):
            emptyval = [0.0] * c.size
            # bool([])==false
            b.values = [bool(x) for x in c.values]
            c.values = [x if x else emptyval for x in c.values]

        self.table.addData(columns)


    def addPartialData(self, cols, copy=True):
        """
        Add a new row of data where some DoubleArray columns may be omitted
        @param cols A subset of the columns obtained from getHeaders() whose
        values have been filled with the data to be added. Missing columns
        are automatically treated as nulls.
        """
        columns = self.table.getHeaders()
        nCols = len(columns) / 2

        if copy:
            cols = deepcopy(cols)
        columnMap = dict([(c.name, c) for c in cols])

        # Check the first id column is present
        idColName = columns[0].name
        try:
            columns[0] = columnMap.pop(idColName)
        except KeyError:
            raise TableConnectionError(
                "First column (%s) must be provided" % idCol.name)

        nRows = len(columns[0].values)
        columns[nCols].values = [True] * nRows

        for n in xrange(1, nCols):
            try:
                columns[n] = columnMap.pop(columns[n].name)
                self._zeroEmptyColumns(columns[n], columns[nCols + n])
            except KeyError:
                columns[n].values = [[0.0] * columns[n].size] * nRows
                columns[nCols + n].values = [False] * nRows

            if not isinstance(columns[n], DoubleArrayColumn):
                raise TableConnectionError(
                    "Expected DoubleArrayColumn (%s)" % columns[n].name)

        if columnMap.keys():
            raise TableConnectionError(
                "Unexpected columns: %s" % columnMap.keys())

        self.table.addData(columns)


    def _zeroEmptyColumns(self, col, bcol):
        """
        Internal helper method, sets empty elements to zeros and the
        corresponding boolean indicator column entry to False
        @param col The data column
        @param bcol The indicator column
        """
        #for (c, b) in izip(columns[1:nCols], columns[(nCols + 1):]):
        emptyval = [0.0] * col.size
        bcol.values = [bool(x) for x in col.values]
        col.values = [x if x else emptyval for x in col.values]


    def _nullEmptyColumns(self, col, bcol):
        """
        Internal helper method, sets column elements which are indicated by
        the boolean indicator as empty to [] if they are array-columns, or
        None for scalar column types
        @param col The data column
        @param bcol The indicator column
        """
        if isinstance(col, (LongArrayColumn, DoubleArrayColumn)):
            col.values = [x if y else []
                          for (x, y) in izip(col.values, bcol.values)]
        else:
            col.values = [x if y else None
                          for (x, y) in izip(col.values, bcol.values)]


    def _checkColNumbers(self, colNumbers):
        """
        Checks the requested column numbers refer to the id or
        double-array-columns, and not the boolean indicator columns
        @param colNumbers A list of data column numbers
        @return The number of data columns (including the ID column if
        requested) but excluding the boolean indicator columns
        """
        nCols = len(self.table.getHeaders()) / 2
        invalid = filter(lambda x: x >= nCols, colNumbers)
        if len(invalid) > 0:
            raise TableConnectionError("Invalid column index: %s" % invalid)

        return nCols

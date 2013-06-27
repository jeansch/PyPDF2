# -*- coding: utf-8 -*-
#
# Copyright (c) 2006, Mathieu Fenniak
# Copyright (c) 2007, Ashish Kulkarni <kulkarni.ashish@gmail.com>
# Copyright (c) 2013, Jean Schurger <jean@schurger.org>
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# * The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import sys
import struct
from StringIO import StringIO

from hashlib import md5

import utils
from utils import b_
from utils import readNonWhitespace, readUntilWhitespace
import warnings
from generic import DictionaryObject, ArrayObject, NameObject, BooleanObject
from generic import IndirectObject, NumberObject, StreamObject
from generic import readObject, createStringObject

from generic import ByteStringObject, TextStringObject
from algorithms import _alg34, _alg35, _alg33_1
from page_object import PageObject
from destination import Destination
from utils import ConvertFunctionsToVirtualList
from document_information import DocumentInformation

warnings.formatwarning = utils._formatwarning

import __builtin__
__builtin__.UserWarning


def convertToInt(d, size):
    if size > 8:
        raise utils.PdfReadError("invalid size in convertToInt")
    d = "\x00\x00\x00\x00\x00\x00\x00\x00" + d
    d = d[-8:]
    return struct.unpack(">q", d)[0]


##
# Initializes a PdfFileReader object.  This operation can take some time, as
# the PDF stream's cross-reference tables are read into memory.
# <p>
# Stability: Added in v1.0, will exist for all v1.x releases.
#
# @param stream An object that supports the standard read and seek methods
#               similar to a file object.
# @param strict Determines whether user should be warned of all problems and
#               also causes some correctable problems to be fatal. Defaults
#               to False.
# @param warndest Allows redirection of warnings to any open file/stream.
#               Defauls to the warnings default (sys.stderr)
class PdfFileReader(object):
    def __init__(self, stream, strict=True, warndest=None):
        # have to dynamically override the default show
        # warning since there are no public methods that specify
        # the 'file' parameter
        def _showwarning(message, category, filename,
                         lineno, file=warndest, line=None):
            if file is None:
                file = sys.stderr
            try:
                file.write(warnings.formatwarning(message, category,
                                                  filename, lineno, line))
            except IOError:
                pass
        warnings.showwarning = _showwarning
        self.strict = strict
        self.flattenedPages = None
        self.resolvedObjects = {}
        self.xrefIndex = 0
        if hasattr(stream, 'mode') and 'b' not in stream.mode:
            warnings.warn("PdfFileReader stream/file object is not in binary "
                          "mode. It may not be read correctly.",
                          utils.PdfReadWarning)
        if type(stream) in (str, unicode):
            fileobj = open(stream, 'rb')
            stream = StringIO(fileobj.read())
            fileobj.close()
        self.read(stream)
        self.stream = stream
        self._override_encryption = False

    ##
    # Retrieves the PDF file's document information dictionary, if it exists.
    # Note that some PDF files use metadata streams instead of docinfo
    # dictionaries, and these metadata streams will not be accessed by this
    # function.
    # <p>
    # Stability: Added in v1.6, will exist for all future v1.x releases.
    # @return Returns a {@link #DocumentInformation DocumentInformation}
    #         instance, or None if none exists.
    def getDocumentInfo(self):
        if "/Info" not in self.trailer:
            return None
        obj = self.trailer['/Info']
        retval = DocumentInformation()
        retval.update(obj)
        return retval

    ##
    # Read-only property that accesses the {@link
    # #PdfFileReader.getDocumentInfo getDocumentInfo} function.
    # <p>
    # Stability: Added in v1.7, will exist for all future v1.x releases.
    documentInfo = property(lambda self: self.getDocumentInfo(), None, None)

    ##
    # Retrieves XMP (Extensible Metadata Platform) data from the PDF document
    # root.
    # <p>
    # Stability: Added in v1.12, will exist for all future v1.x releases.
    # @return Returns a {@link #generic.XmpInformation XmlInformation}
    # instance that can be used to access XMP metadata from the document.
    # Can also return None if no metadata was found on the document root.
    def getXmpMetadata(self):
        try:
            self._override_encryption = True
            return self.trailer["/Root"].getXmpMetadata()
        finally:
            self._override_encryption = False

    ##
    # Read-only property that accesses the {@link #PdfFileReader.getXmpData
    # getXmpData} function.
    # <p>
    # Stability: Added in v1.12, will exist for all future v1.x releases.
    xmpMetadata = property(lambda self: self.getXmpMetadata(), None, None)

    ##
    # Calculates the number of pages in this PDF file.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    # @return Returns an integer.
    def getNumPages(self):
        # Flattened pages will not work on an Encrypted PDF
        # the PDF file's page count is used in this case. Otherwise,
        # the original method (flattened page count) is used.
        if self.isEncrypted:
            try:
                self._override_encryption = True
                return self.trailer["/Root"]["/Pages"]["/Count"]
            finally:
                self._override_encryption = False
        else:
            if self.flattenedPages is None:
                self._flatten()
            return len(self.flattenedPages)

    ##
    # Read-only property that accesses the {@link #PdfFileReader.getNumPages
    # getNumPages} function.
    # <p>
    # Stability: Added in v1.7, will exist for all future v1.x releases.
    numPages = property(lambda self: self.getNumPages(), None, None)

    ##
    # Retrieves a page by number from this PDF file.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    # @return Returns a {@link #PageObject PageObject} instance.
    def getPage(self, pageNumber):
        ## ensure that we're not trying to access an encrypted PDF
        #assert not self.trailer.has_key("/Encrypt")
        if self.flattenedPages is None:
            self._flatten()
        return self.flattenedPages[pageNumber]

    ##
    # Read-only property that accesses the
    # {@link #PdfFileReader.getNamedDestinations
    # getNamedDestinations} function.
    # <p>
    # Stability: Added in v1.10, will exist for all future v1.x releases.
    namedDestinations = property(lambda self: self.getNamedDestinations(),
                                 None, None)

    ##
    # Retrieves the named destinations present in the document.
    # <p>
    # Stability: Added in v1.10, will exist for all future v1.x releases.
    # @return Returns a dict which maps names to {@link #Destination
    # destinations}.
    def getNamedDestinations(self, tree=None, retval=None):
        if retval is None:
            retval = {}
            catalog = self.trailer["/Root"]
            # get the name tree
            if "/Dests" in catalog:
                tree = catalog["/Dests"]
            elif "/Names" in catalog:
                names = catalog['/Names']
                if "/Dests" in names:
                    tree = names['/Dests']
        if tree is None:
            return retval
        if "/Kids" in tree:
            # recurse down the tree
            for kid in tree["/Kids"]:
                self.getNamedDestinations(kid.getObject(), retval)

        if "/Names" in tree:
            names = tree["/Names"]
            for i in range(0, len(names), 2):
                key = names[i].getObject()
                val = names[i+1].getObject()
                if isinstance(val, DictionaryObject) and '/D' in val:
                    val = val['/D']
                dest = self._buildDestination(key, val)
                if dest is not None:
                    retval[key] = dest

        return retval

    ##
    # Read-only property that accesses the {@link #PdfFileReader.getOutlines
    # getOutlines} function.
    # <p>
    # Stability: Added in v1.10, will exist for all future v1.x releases.
    outlines = property(lambda self: self.getOutlines(), None, None)

    ##
    # Retrieves the document outline present in the document.
    # <p>
    # Stability: Added in v1.10, will exist for all future v1.x releases.
    # @return Returns a nested list of {@link #Destination destinations}.
    def getOutlines(self, node=None, outlines=None):
        if outlines is None:
            outlines = []
            catalog = self.trailer["/Root"]
            # get the outline dictionary and named destinations
            if "/Outlines" in catalog:
                lines = catalog["/Outlines"]
                if "/First" in lines:
                    node = lines["/First"]
            self._namedDests = self.getNamedDestinations()
        if node is None:
            return outlines
        # see if there are any more outlines
        while 1:
            outline = self._buildOutline(node)
            if outline:
                outlines.append(outline)

            # check for sub-outlines
            if "/First" in node:
                subOutlines = []
                self.getOutlines(node["/First"], subOutlines)
                if subOutlines:
                    outlines.append(subOutlines)
            if "/Next" not in node:
                break
            node = node["/Next"]

        return outlines

    def _buildDestination(self, title, array):
        page, typ = array[0:2]
        array = array[2:]
        return Destination(title, page, typ, *array)

    def _buildOutline(self, node):
        dest, title, outline = None, None, None
        if "/A" in node and "/Title" in node:
            # Action, section 8.5 (only type GoTo supported)
            title = node["/Title"]
            action = node["/A"]
            if action["/S"] == "/GoTo":
                dest = action["/D"]
        elif "/Dest" in node and "/Title" in node:
            # Destination, section 8.2.1
            title = node["/Title"]
            dest = node["/Dest"]

        # if destination found, then create outline
        if dest:
            if isinstance(dest, ArrayObject):
                outline = self._buildDestination(title, dest)
            elif isinstance(dest, unicode) and dest in self._namedDests:
                outline = self._namedDests[dest]
                outline[NameObject("/Title")] = title
            else:
                raise utils.PdfReadError("Unexpected destination %r" % dest)
        return outline

    ##
    # Read-only property that emulates a list based upon the {@link
    # #PdfFileReader.getNumPages getNumPages} and {@link #PdfFileReader.getPage
    # getPage} functions.
    # <p>
    # Stability: Added in v1.7, and will exist for all future v1.x releases.
    pages = property(lambda self: ConvertFunctionsToVirtualList(
        self.getNumPages, self.getPage), None, None)

    def _flatten(self, pages=None, inherit=None, indirectRef=None):
        inheritablePageAttributes = (NameObject("/Resources"),
                                     NameObject("/MediaBox"),
                                     NameObject("/CropBox"),
                                     NameObject("/Rotate"))
        if inherit is None:
            inherit = dict()
        if pages is None:
            self.flattenedPages = []
            catalog = self.trailer["/Root"].getObject()
            pages = catalog["/Pages"].getObject()
        t = pages["/Type"]
        if t == "/Pages":
            for attr in inheritablePageAttributes:
                if attr in pages:
                    inherit[attr] = pages[attr]
            for page in pages["/Kids"]:
                addt = {}
                if isinstance(page, IndirectObject):
                    addt["indirectRef"] = page
                self._flatten(page.getObject(), inherit, **addt)
        elif t == "/Page":
            for attr, value in inherit.items():
                # if the page has it's own value, it does not inherit the
                # parent's value:
                if attr not in pages:
                    pages[attr] = value
            pageObj = PageObject(self, indirectRef)
            pageObj.update(pages)
            self.flattenedPages.append(pageObj)

    def getObject(self, indirectReference):
        retval = self.resolvedObjects.get(indirectReference.generation,
                                          {}).get(indirectReference.idnum,
                                                  None)
        if retval is not None:
            return retval
        if indirectReference.generation == 0 \
                and indirectReference.idnum in self.xref_objStm:
            # indirect reference to object in object stream
            # read the entire object stream into memory
            stmnum, idx = self.xref_objStm[indirectReference.idnum]
            objStm = IndirectObject(stmnum, 0, self).getObject()
            assert objStm['/Type'] == '/ObjStm'
            assert idx < objStm['/N']
            streamData = StringIO(objStm.getData())
            for i in range(objStm['/N']):
                objnum = NumberObject.readFromStream(streamData)
                readNonWhitespace(streamData)
                streamData.seek(-1, 1)
                offset = NumberObject.readFromStream(streamData)
                readNonWhitespace(streamData)
                streamData.seek(-1, 1)
                t = streamData.tell()
                streamData.seek(objStm['/First']+offset, 0)
                obj = readObject(streamData, self)
                self.resolvedObjects[0][objnum] = obj
                streamData.seek(t, 0)
            return self.resolvedObjects[0][indirectReference.idnum]
        if indirectReference.idnum \
                not in self.xref[indirectReference.generation]:
            warnings.warn("Object %d %d not defined." % (
                indirectReference.idnum, indirectReference.generation),
                utils.PdfReadWarning)
            return None
        start = self.xref[indirectReference.generation][
            indirectReference.idnum]
        self.stream.seek(start, 0)
        idnum, generation = self.readObjectHeader(self.stream)
        try:
            assert idnum == indirectReference.idnum
        except AssertionError:
            if self.xrefIndex:
                # Xref table probably had bad indexes due to not
                # being zero-indexed
                if self.strict:
                    raise utils.PdfReadError(
                        "Expected object ID (%d %d) does "
                        "not match actual (%d %d); xref "
                        "table not zero-indexed." % (
                            indirectReference.idnum,
                            indirectReference.generation,
                            idnum,
                            generation))
                else:
                    # should not happen since the xref table is corrected in
                    # non-strict mode
                    pass
            else:  # some other problem
                raise utils.PdfReadError("Expected object ID (%d %d) does not "
                                         " match actual (%d %d)." % (
                                             indirectReference.idnum,
                                             indirectReference.generation,
                                             idnum, generation))
        assert generation == indirectReference.generation
        retval = readObject(self.stream, self)
        # override encryption is used for the /Encrypt dictionary
        if not self._override_encryption and self.isEncrypted:
            # if we don't have the encryption key:
            if not hasattr(self, '_decryption_key'):
                raise Exception("file has not been decrypted")
            # otherwise, decrypt here...
            pack1 = struct.pack("<i", indirectReference.idnum)[:3]
            pack2 = struct.pack("<i", indirectReference.generation)[:2]
            key = self._decryption_key + pack1 + pack2
            assert len(key) == (len(self._decryption_key) + 5)
            md5_hash = md5(key).digest()
            key = md5_hash[:min(16, len(self._decryption_key) + 5)]
            retval = self._decryptObject(retval, key)

        self.cacheIndirectObject(generation, idnum, retval)
        return retval

    def _decryptObject(self, obj, key):
        if isinstance(obj, ByteStringObject) \
                or isinstance(obj, TextStringObject):
            obj = createStringObject(utils.RC4_encrypt(key,
                                                       obj.original_bytes))
        elif isinstance(obj, StreamObject):
            obj._data = utils.RC4_encrypt(key, obj._data)
        elif isinstance(obj, DictionaryObject):
            for dictkey, value in obj.items():
                obj[dictkey] = self._decryptObject(value, key)
        elif isinstance(obj, ArrayObject):
            for i in range(len(obj)):
                obj[i] = self._decryptObject(obj[i], key)
        return obj

    def readObjectHeader(self, stream):
        # Should never be necessary to read out whitespace, since the
        # cross-reference table should put us in the right spot to read the
        # object header.  In reality... some files have stupid cross reference
        # tables that are off by whitespace bytes.
        extra = False
        utils.skipOverComment(stream)

        extra |= utils.skipOverWhitespace(stream)
        stream.seek(-1, 1)

        idnum = readUntilWhitespace(stream)

        extra |= utils.skipOverWhitespace(stream)
        stream.seek(-1, 1)

        generation = readUntilWhitespace(stream)
        stream.read(3)
        readNonWhitespace(stream)
        stream.seek(-1, 1)
        if (extra and self.strict):
            #not a fatal error
            warnings.warn("Superfluous whitespace found in "
                          "object header %s %s" % (idnum, generation),
                          utils.PdfReadWarning)
        return int(idnum), int(generation)

    def cacheIndirectObject(self, generation, idnum, obj):
        self.resolvedObjects.setdefault(generation, {})
        self.resolvedObjects[generation][idnum] = obj

    def read(self, stream):
        # start at the end:
        stream.seek(-1, 2)
        line = b_('')
        while not line:
            line = self.readNextEndLine(stream)
        if line[:5] != b_("%%EOF"):
            raise utils.PdfReadError, "EOF marker not found"
        # find startxref entry - the location of the xref table
        line = self.readNextEndLine(stream)
        startxref = int(line)
        line = self.readNextEndLine(stream)
        if line[:9] != b_("startxref"):
            raise utils.PdfReadError, "startxref not found"

        # read all cross reference tables and their trailers
        self.xref = {}
        self.xref_objStm = {}
        self.trailer = DictionaryObject()
        while 1:
            # load the xref table
            stream.seek(startxref, 0)
            x = stream.read(1)
            if x == b_("x"):
                # standard cross-reference table
                ref = stream.read(4)
                if ref[:3] != b_("ref"):
                    raise utils.PdfReadError, "xref table read error"
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                # check if the first time looking at the xref table
                firsttime = True
                while True:
                    num = readObject(stream, self)
                    if firsttime and num != 0:
                        self.xrefIndex = num
                        warnings.warn("Xref table not zero-indexed. ID "
                                      "numbers for objects will %sbe "
                                      "corrected." %
                                      ("" if not self.strict else "not "),
                                      utils.PdfReadWarning)
                         # if table not zero indexed, could be due to
                         # error from when PDF was created
                         # which will lead to mismatched indices later on
                    firsttime = False
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    size = readObject(stream, self)
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    cnt = 0
                    while cnt < size:
                        line = stream.read(20)
                        # It's very clear in section 3.4.3 of the PDF spec
                        # that all cross-reference table lines are a fixed
                        # 20 bytes (as of PDF 1.7). However, some files have
                        # 21-byte entries (or more) due to the use of \r\n
                        # (CRLF) EOL's. Detect that case, and adjust the line
                        # until it does not begin with a \r (CR) or \n (LF).
                        while line[0] in b_("\x0D\x0A"):
                            stream.seek(-20 + 1, 1)
                            line = stream.read(20)
                        # On the other hand, some malformed PDF files
                        # use a single character EOL without a preceeding
                        # space.  Detect that case, and seek the stream
                        # back one character.  (0-9 means we've bled into
                        # the next xref entry, t means we've bled into the
                        # text "trailer"):
                        if line[-1] in b_("0123456789t"):
                            stream.seek(-1, 1)
                        offset, generation = line[:16].split(b_(" "))
                        offset, generation = int(offset), int(generation)
                        self.xref.setdefault(generation, {})
                        if num in self.xref[generation]:
                            # It really seems like we should allow the last
                            # xref table in the file to override previous
                            # ones. Since we read the file backwards, assume
                            # any existing key is already set correctly.
                            pass
                        else:
                            self.xref[generation][num] = offset
                        cnt += 1
                        num += 1
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    trailertag = stream.read(7)
                    if trailertag != b_("trailer"):
                        # more xrefs!
                        stream.seek(-7, 1)
                    else:
                        break
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                newTrailer = readObject(stream, self)
                for key, value in newTrailer.items():
                    self.trailer.setdefault(key, value)
                if "/Prev" in newTrailer:
                    startxref = newTrailer["/Prev"]
                else:
                    break
            elif x.isdigit():
                # PDF 1.5+ Cross-Reference Stream
                stream.seek(-1, 1)
                idnum, generation = self.readObjectHeader(stream)
                xrefstream = readObject(stream, self)
                assert xrefstream["/Type"] == "/XRef"
                self.cacheIndirectObject(generation, idnum, xrefstream)
                streamData = StringIO(xrefstream.getData())
                idx_pairs = xrefstream.get("/Index",
                                           [0, xrefstream.get("/Size")])
                entrySizes = xrefstream.get("/W")
                for num, size in self._pairs(idx_pairs):
                    cnt = 0
                    while cnt < size:
                        for i in range(len(entrySizes)):
                            d = streamData.read(entrySizes[i])
                            di = convertToInt(d, entrySizes[i])
                            if i == 0:
                                xref_type = di
                            elif i == 1:
                                if xref_type == 0:
                                    # next_free_object = di
                                    pass
                                elif xref_type == 1:
                                    byte_offset = di
                                elif xref_type == 2:
                                    objstr_num = di
                            elif i == 2:
                                if xref_type == 0:
                                    # next_generation = di
                                    pass
                                elif xref_type == 1:
                                    generation = di
                                elif xref_type == 2:
                                    obstr_idx = di
                        if xref_type == 0:
                            pass
                        elif xref_type == 1:
                            if generation not in self.xref:
                                self.xref[generation] = {}
                            if not num in self.xref[generation]:
                                self.xref[generation][num] = byte_offset
                        elif xref_type == 2:
                            if not num in self.xref_objStm:
                                self.xref_objStm[num] = [objstr_num, obstr_idx]
                        cnt += 1
                        num += 1
                trailerKeys = "/Root", "/Encrypt", "/Info", "/ID"
                for key in trailerKeys:
                    if key in xrefstream and key not in self.trailer:
                        self.trailer[NameObject(key)] = xrefstream.raw_get(key)
                if "/Prev" in xrefstream:
                    startxref = xrefstream["/Prev"]
                else:
                    break
            else:
                # bad xref character at startxref.  Let's see if we can find
                # the xref table nearby, as we've observed this error with an
                # off-by-one before.
                stream.seek(-11, 1)
                tmp = stream.read(20)
                xref_loc = tmp.find(b_("xref"))
                if xref_loc != -1:
                    startxref -= (10 - xref_loc)
                    continue
                else:
                    # no xref table found at specified location
                    assert False
                    break
        # if not zero-indexed, verify that the table is correct
        # change it if necessary
        if self.xrefIndex and not self.strict:
            loc = stream.tell()
            for gen in self.xref:
                if gen == 65535:
                    continue
                for id in self.xref[gen]:
                    stream.seek(self.xref[gen][id], 0)
                    pid, pgen = self.readObjectHeader(stream)
                    if pid == id - self.xrefIndex:
                        self._zeroXref(gen)
                        break
                    # if not, then either it's just plain wrong,
                    # or the non-zero-index is actually correct
            stream.seek(loc, 0)  # return to where it was

    def _zeroXref(self, generation):
        self.xref[generation] = dict((k-self.xrefIndex, v) for (k, v)
                                     in self.xref[generation].iteritems())

    def _pairs(self, array):
        i = 0
        while True:
            yield array[i], array[i+1]
            i += 2
            if (i+1) >= len(array):
                break

    def readNextEndLine(self, stream):
        line = b_("")
        while True:
            x = stream.read(1)
            stream.seek(-2, 1)
            if x == b_('\n') or x == b_('\r'):  # \n = LF; \r = CR
                crlf = False
                while x == b_('\n') or x == b_('\r'):
                    x = stream.read(1)
                    if x == b_('\n') or x == b_('\r'):  # account for CR+LF
                        stream.seek(-1, 1)
                        crlf = True
                    stream.seek(-2, 1)
                # if using CR+LF, go back 2 bytes, else 1
                stream.seek(2 if crlf else 1, 1)
                break
            else:
                line = x + line
        return line

    ##
    # When using an encrypted / secured PDF file with the PDF Standard
    # encryption handler, this function will allow the file to be decrypted.
    # It checks the given password against the document's user password and
    # owner password, and then stores the resulting decryption key if either
    # password is correct.
    # <p>
    # It does not matter which password was matched.  Both passwords provide
    # the correct decryption key that will allow the document to be used with
    # this library.
    # <p>
    # Stability: Added in v1.8, will exist for all future v1.x releases.
    #
    # @return 0 if the password failed, 1 if the password matched the user
    # password, and 2 if the password matched the owner password.
    #
    # @exception NotImplementedError Document uses an unsupported encryption
    # method.
    def decrypt(self, password):
        self._override_encryption = True
        try:
            return self._decrypt(password)
        finally:
            self._override_encryption = False

    def _decrypt(self, password):
        encrypt = self.trailer['/Encrypt'].getObject()
        if encrypt['/Filter'] != '/Standard':
            raise NotImplementedError(
                "only Standard PDF encryption handler is available")
        if not (encrypt['/V'] in (1, 2)):
            raise NotImplementedError(
                "only algorithm code 1 and 2 are supported")
        user_password, key = self._authenticateUserPassword(password)
        if user_password:
            self._decryption_key = key
            return 1
        else:
            rev = encrypt['/R'].getObject()
            if rev == 2:
                keylen = 5
            else:
                keylen = encrypt['/Length'].getObject() // 8
            key = _alg33_1(password, rev, keylen)
            real_O = encrypt["/O"].getObject()
            if rev == 2:
                userpass = utils.RC4_encrypt(key, real_O)
            else:
                val = real_O
                for i in range(19, -1, -1):
                    new_key = b_('')
                    for l in range(len(key)):
                        new_key += b_(chr(utils.ord_(key[l]) ^ i))
                    val = utils.RC4_encrypt(new_key, val)
                userpass = val
            owner_password, key = self._authenticateUserPassword(userpass)
            if owner_password:
                self._decryption_key = key
                return 2
        return 0

    def _authenticateUserPassword(self, password):
        encrypt = self.trailer['/Encrypt'].getObject()
        rev = encrypt['/R'].getObject()
        owner_entry = encrypt['/O'].getObject().original_bytes
        p_entry = encrypt['/P'].getObject()
        id_entry = self.trailer['/ID'].getObject()
        id1_entry = id_entry[0].getObject()
        real_U = encrypt['/U'].getObject().original_bytes
        if rev == 2:
            U, key = _alg34(password, owner_entry, p_entry, id1_entry)
        elif rev >= 3:
            U, key = _alg35(password, rev,
                            encrypt["/Length"].getObject() // 8, owner_entry,
                            p_entry, id1_entry,
                            encrypt.get("/EncryptMetadata",
                                        BooleanObject(False)).getObject())
            U, real_U = U[:16], real_U[:16]
        return U == real_U, key

    def getIsEncrypted(self):
        return "/Encrypt" in self.trailer

    ##
    # Read-only boolean property showing whether this PDF file is encrypted.
    # Note that this property, if true, will remain true even after the {@link
    # #PdfFileReader.decrypt decrypt} function is called.
    isEncrypted = property(lambda self: self.getIsEncrypted(), None, None)

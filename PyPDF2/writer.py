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

from hashlib import md5
import struct

from utils import b_
from algorithms import _alg33, _alg34, _alg35
from generic import DictionaryObject, NameObject, ArrayObject, NumberObject
from generic import IndirectObject, ByteStringObject, StreamObject
from generic import TreeObject, createStringObject
from page_object import PageObject


##
# This class supports writing PDF files out, given pages produced by another

# class (typically {@link #PdfFileReader PdfFileReader}).
class PdfFileWriter(object):
    def __init__(self):
        self._header = b_("%PDF-1.3")
        self._objects = []  # array of indirect objects
        # The root of our page tree node.
        pages = DictionaryObject()
        pages.update({NameObject("/Type"): NameObject("/Pages"),
                      NameObject("/Count"): NumberObject(0),
                      NameObject("/Kids"): ArrayObject()})
        self._pages = self._addObject(pages)
        # info object
        info = DictionaryObject()
        info.update({NameObject("/Producer"): createStringObject(
            u"Python PDF Library - http://pybrary.net/pyPdf/")})
        self._info = self._addObject(info)
        # root object
        root = DictionaryObject()
        root.update({NameObject("/Type"): NameObject("/Catalog"),
                     NameObject("/Pages"): self._pages})
        self._root = self._addObject(root)

    def _addObject(self, obj):
        self._objects.append(obj)
        return IndirectObject(len(self._objects), 0, self)

    def getObject(self, ido):
        if ido.pdf != self:
            raise ValueError("pdf must be self")
        ret = self._objects[ido.idnum - 1]
        return ret

    ##
    # Common method for inserting or adding a page to this PDF file.
    #
    # @param page The page to add to the document.  This argument should be
    #             an instance of {@link #PageObject PageObject}.
    # @param action The function which will insert the page in the dictionnary.
    #               Takes: page list, page to add.
    def _addPage(self, page, action):
        assert page["/Type"] == "/Page"
        page[NameObject("/Parent")] = self._pages
        page = self._addObject(page)
        pages = self.getObject(self._pages)
        action(pages["/Kids"], page)
        pages[NameObject("/Count")] = NumberObject(pages["/Count"] + 1)

    ##
    # Adds a page to this PDF file.  The page is usually acquired from a
    # {@link #PdfFileReader PdfFileReader} instance.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    #
    # @param page The page to add to the document.  This argument should be
    #             an instance of {@link #PageObject PageObject}.
    def addPage(self, page):
        self._addPage(page, list.append)

    ##
    # Insert a page in this PDF file.  The page is usually acquired from a
    # {@link #PdfFileReader PdfFileReader} instance.
    #
    # @param page The page to add to the document.  This argument should be
    #             an instance of {@link #PageObject PageObject}.
    # @param index Position at which the page will be inserted.
    def insertPage(self, page, index=0):
        self._addPage(page, lambda l, p: l.insert(index, p))

    ##
    # Retrieves a page by number from this PDF file.
    # @return Returns a {@link #PageObject PageObject} instance.
    def getPage(self, pageNumber):
        pages = self.getObject(self._pages)
        # XXX: crude hack
        return pages["/Kids"][pageNumber].getObject()

    ##
    # Return the number of pages.
    # @return The number of pages.
    def getNumPages(self):
        pages = self.getObject(self._pages)
        return int(pages[NameObject("/Count")])

    ##
    # Append a blank page to this PDF file and returns it. If no page size
    # is specified, use the size of the last page; throw
    # PageSizeNotDefinedError if it doesn't exist.
    # @param width The width of the new page expressed in default user
    # space units.
    # @param height The height of the new page expressed in default user
    # space units.
    def addBlankPage(self, width=None, height=None):
        page = PageObject.createBlankPage(self, width, height)
        self.addPage(page)
        return page

    ##
    # Insert a blank page to this PDF file and returns it. If no page size
    # is specified, use the size of the page in the given index; throw
    # PageSizeNotDefinedError if it doesn't exist.
    # @param width  The width of the new page expressed in default user
    #               space units.
    # @param height The height of the new page expressed in default user
    #               space units.
    # @param index  Position to add the page.
    def insertBlankPage(self, width=None, height=None, index=0):
        if width is None or height is None and \
                (self.getNumPages() - 1) >= index:
            oldpage = self.getPage(index)
            width = oldpage.mediaBox.getWidth()
            height = oldpage.mediaBox.getHeight()
        page = PageObject.createBlankPage(self, width, height)
        self.insertPage(page, index)
        return page

    ##
    # Encrypt this PDF file with the PDF Standard encryption handler.
    # @param user_pwd The "user password", which allows for opening and reading
    # the PDF file with the restrictions provided.
    # @param owner_pwd The "owner password", which allows for opening the PDF
    # files without any restrictions.  By default, the owner password is the
    # same as the user password.
    # @param use_128bit Boolean argument as to whether to use 128bit
    # encryption.  When false, 40bit encryption will be used.  By default, this
    # flag is on.
    def encrypt(self, user_pwd, owner_pwd=None, use_128bit=True):
        import time
        import random
        if owner_pwd is None:
            owner_pwd = user_pwd
        if use_128bit:
            V = 2
            rev = 3
            keylen = 128 / 8
        else:
            V = 1
            rev = 2
            keylen = 40 / 8
        # permit everything:
        P = -1
        O = ByteStringObject(_alg33(owner_pwd, user_pwd, rev, keylen))
        ID_1 = md5(repr(time.time())).digest()
        ID_2 = md5(repr(random.random())).digest()
        self._ID = ArrayObject((ByteStringObject(ID_1),
                                ByteStringObject(ID_2)))
        if rev == 2:
            U, key = _alg34(user_pwd, O, P, ID_1)
        else:
            assert rev == 3
            U, key = _alg35(user_pwd, rev, keylen, O, P, ID_1, False)
        encrypt = DictionaryObject()
        encrypt[NameObject("/Filter")] = NameObject("/Standard")
        encrypt[NameObject("/V")] = NumberObject(V)
        if V == 2:
            encrypt[NameObject("/Length")] = NumberObject(keylen * 8)
        encrypt[NameObject("/R")] = NumberObject(rev)
        encrypt[NameObject("/O")] = ByteStringObject(O)
        encrypt[NameObject("/U")] = ByteStringObject(U)
        encrypt[NameObject("/P")] = NumberObject(P)
        self._encrypt = self._addObject(encrypt)
        self._encrypt_key = key

    ##
    # Writes the collection of pages added to this object out as a PDF file.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    # @param stream An object to write the file to.  The object must support
    # the write method, and the tell method, similar to a file object.
    def write(self, stream):
        externalReferenceMap = {}

        # PDF objects sometimes have circular references to their /Page objects
        # inside their object tree (for example, annotations).  Those will be
        # indirect references to objects that we've recreated in this PDF.  To
        # address this problem, PageObject's store their original object
        # reference number, and we add it to the external reference map before
        # we sweep for indirect references.  This forces self-page-referencing
        # trees to reference the correct new object location, rather than
        # copying in a new copy of the page object.
        for objIndex in xrange(len(self._objects)):
            obj = self._objects[objIndex]
            if isinstance(obj, PageObject) and obj.indirectRef is not None:
                data = obj.indirectRef
                externalReferenceMap.setdefault(data.pdf, {})
                externalReferenceMap[data.pdf].setdefault(data.generation, {})
                externalReferenceMap[data.pdf][data.generation][data.idnum] = \
                    IndirectObject(objIndex + 1, 0, self)

        self.stack = []
        self._sweepIndirectReferences(externalReferenceMap, self._root)
        del self.stack

        # Begin writing:
        object_positions = []
        stream.write(self._header + b_("\n"))
        for i in range(len(self._objects)):
            idnum = (i + 1)
            obj = self._objects[i]
            object_positions.append(stream.tell())
            stream.write(b_(str(idnum) + " 0 obj\n"))
            key = None
            if hasattr(self, "_encrypt") and idnum != self._encrypt.idnum:
                pack1 = struct.pack("<i", i + 1)[:3]
                pack2 = struct.pack("<i", 0)[:2]
                key = self._encrypt_key + pack1 + pack2
                assert len(key) == (len(self._encrypt_key) + 5)
                md5_hash = md5(key).digest()
                key = md5_hash[:min(16, len(self._encrypt_key) + 5)]
            if obj is not None:
                obj.writeToStream(stream, key)
                stream.write(b_("\nendobj\n"))

        # xref table
        xref_location = stream.tell()
        stream.write(b_("xref\n"))
        stream.write(b_("0 %s\n" % (len(self._objects) + 1)))
        stream.write(b_("%010d %05d f \n" % (0, 65535)))
        for offset in object_positions:
            stream.write(b_("%010d %05d n \n" % (offset, 0)))

        # trailer
        stream.write(b_("trailer\n"))
        trailer = DictionaryObject()
        trailer.update({NameObject("/Size"): NumberObject(
            len(self._objects) + 1),
            NameObject("/Root"): self._root,
            NameObject("/Info"): self._info})
        if hasattr(self, "_ID"):
            trailer[NameObject("/ID")] = self._ID
        if hasattr(self, "_encrypt"):
            trailer[NameObject("/Encrypt")] = self._encrypt
        trailer.writeToStream(stream, None)

        # eof
        stream.write(b_("\nstartxref\n%s\n%%%%EOF\n" % (xref_location)))

    def _sweepIndirectReferences(self, externMap, data):
        if isinstance(data, DictionaryObject):
            for key, value in data.items():
                value = self._sweepIndirectReferences(externMap, value)
                if isinstance(value, StreamObject):
                    # a dictionary value is a stream.  streams must be indirect
                    # objects, so we need to change this value.
                    value = self._addObject(value)
                data[key] = value
            return data
        elif isinstance(data, ArrayObject):
            for i in range(len(data)):
                value = self._sweepIndirectReferences(externMap, data[i])
                if isinstance(value, StreamObject):
                    # an array value is a stream.  streams must be indirect
                    # objects, so we need to change this value
                    value = self._addObject(value)
                data[i] = value
            return data
        elif isinstance(data, IndirectObject):
            # internal indirect references are fine
            if data.pdf == self:
                if data.idnum in self.stack:
                    return data
                else:
                    self.stack.append(data.idnum)
                    realdata = self.getObject(data)
                    self._sweepIndirectReferences(externMap, realdata)
                    self.stack.pop()
                    return data
            else:
                newobj = externMap.get(data.pdf, {}).get(
                    data.generation, {}).get(data.idnum, None)
                if newobj is None:
                    newobj = data.pdf.getObject(data)
                    self._objects.append(None)  # placeholder
                    idnum = len(self._objects)
                    newobj_ido = IndirectObject(idnum, 0, self)
                    externMap.setdefault(data.pdf, {})
                    externMap[data.pdf].setdefault(data.generation, {})
                    externMap[data.pdf][data.generation][data.idnum] = \
                        newobj_ido
                    newobj = self._sweepIndirectReferences(externMap, newobj)
                    self._objects[idnum-1] = newobj
                    return newobj_ido
                return newobj
        else:
            return data

    def getReference(self, obj):
        idnum = self._objects.index(obj) + 1
        ref = IndirectObject(idnum, 0, self)
        assert ref.getObject() == obj
        return ref

    def getOutlineRoot(self):
        root = self.getObject(self._root)
        if '/Outlines' in root:
            outline = root['/Outlines']
            idnum = self._objects.index(outline) + 1
            outlineRef = IndirectObject(idnum, 0, self)
            assert outlineRef.getObject() == outline
        else:
            outline = TreeObject()
            outline.update({})
            outlineRef = self._addObject(outline)
            root[NameObject('/Outlines')] = outlineRef
        return outline

    def getNamedDestRoot(self):
        root = self.getObject(self._root)

        if '/Names' in root and isinstance(root['/Names'], DictionaryObject):
            names = root['/Names']
            idnum = self._objects.index(names) + 1
            namesRef = IndirectObject(idnum, 0, self)
            assert namesRef.getObject() == names
            if '/Dests' in names and isinstance(
                    names['/Dests'], DictionaryObject):
                dests = names['/Dests']
                idnum = self._objects.index(dests) + 1
                destsRef = IndirectObject(idnum, 0, self)
                assert destsRef.getObject() == dests
                if '/Names' in dests:
                    nd = dests['/Names']
                else:
                    nd = ArrayObject()
                    dests[NameObject('/Names')] = nd
            else:
                dests = DictionaryObject()
                destsRef = self._addObject(dests)
                names[NameObject('/Dests')] = destsRef
                nd = ArrayObject()
                dests[NameObject('/Names')] = nd
        else:
            names = DictionaryObject()
            namesRef = self._addObject(names)
            root[NameObject('/Names')] = namesRef
            dests = DictionaryObject()
            destsRef = self._addObject(dests)
            names[NameObject('/Dests')] = destsRef
            nd = ArrayObject()
            dests[NameObject('/Names')] = nd
        return nd

    def addBookmarkDestination(self, dest, parent=None):
        destRef = self._addObject(dest)
        outlineRef = self.getOutlineRoot()
        if parent is None:
            parent = outlineRef
        parent = parent.getObject()
        parent.addChild(destRef, self)
        return destRef

    def addBookmarkDict(self, bookmark, parent=None):
        bookmarkObj = TreeObject()
        for k, v in bookmark.items():
            bookmarkObj[NameObject(str(k))] = v
        bookmarkObj.update(bookmark)
        if '/A' in bookmark:
            action = DictionaryObject()
            for k, v in bookmark['/A'].items():
                action[NameObject(str(k))] = v
            actionRef = self._addObject(action)
            bookmarkObj['/A'] = actionRef
        bookmarkRef = self._addObject(bookmarkObj)
        outlineRef = self.getOutlineRoot()
        if parent is None:
            parent = outlineRef
        parent = parent.getObject()
        parent.addChild(bookmarkRef, self)
        return bookmarkRef

    def addBookmark(self, title, pagenum, parent=None):
        """
        Add a bookmark to the pdf, using the specified title and pointing at
        the specified page number. A parent can be specified to make this a
        nested bookmark below the parent.
        """
        pageRef = self.getObject(self._pages)['/Kids'][pagenum]
        action = DictionaryObject()
        action.update({NameObject('/D'): ArrayObject([pageRef,
                                                      NameObject('/FitH'),
                                                      NumberObject(826)]),
                       NameObject('/S'): NameObject('/GoTo')})
        actionRef = self._addObject(action)

        outlineRef = self.getOutlineRoot()
        if parent is None:
            parent = outlineRef
        bookmark = TreeObject()
        bookmark.update({NameObject('/A'): actionRef,
                         NameObject('/Title'): createStringObject(title)})
        bookmarkRef = self._addObject(bookmark)

        parent = parent.getObject()
        parent.addChild(bookmarkRef, self)
        return bookmarkRef

    def addNamedDestinationObject(self, dest):
        destRef = self._addObject(dest)

        nd = self.getNamedDestRoot()
        nd.extend([dest['/Title'], destRef])
        return destRef

    def addNamedDestination(self, title, pagenum):
        pageRef = self.getObject(self._pages)['/Kids'][pagenum]
        dest = DictionaryObject()
        dest.update({NameObject('/D'): ArrayObject([pageRef,
                                                    NameObject('/FitH'),
                                                    NumberObject(826)]),
                     NameObject('/S'): NameObject('/GoTo')})
        destRef = self._addObject(dest)
        nd = self.getNamedDestRoot()

        nd.extend([title, destRef])
        return destRef

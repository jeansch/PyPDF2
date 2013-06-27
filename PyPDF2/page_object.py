# -*- coding: utf-8 -*-
#
# Copyright (c) 2006, Mathieu Fenniak
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

from StringIO import StringIO

import math
import utils
from generic import DictionaryObject, NameObject, NullObject
from generic import RectangleObject, NumberObject, readObject
from generic import DecodedStreamObject, ArrayObject, FloatObject
from generic import TextStringObject
from utils import readNonWhitespace
from rectangle import createRectangleAccessor


class ContentStream(DecodedStreamObject):
    def __init__(self, stream, pdf):
        self.pdf = pdf
        self.operations = []
        # stream may be a StreamObject or an ArrayObject containing
        # multiple StreamObjects to be cat'd together.
        stream = stream.getObject()
        if isinstance(stream, ArrayObject):
            data = ""
            for s in stream:
                data += s.getObject().getData()
            stream = StringIO(data)
        else:
            stream = StringIO(stream.getData())
        self.__parseContentStream(stream)

    def __parseContentStream(self, stream):
        stream.seek(0, 0)
        operands = []
        while True:
            peek = readNonWhitespace(stream)
            if peek == '':
                break
            stream.seek(-1, 1)
            if peek.isalpha() or peek == "'" or peek == '"':
                operator = ""
                while True:
                    tok = stream.read(1)
                    if tok.isspace() or tok in NameObject.delimiterCharacters:
                        stream.seek(-1, 1)
                        break
                    elif tok == '':
                        break
                    operator += tok
                if operator == "BI":
                    # begin inline image - a completely different parsing
                    # mechanism is required, of course... thanks buddy...
                    assert operands == []
                    ii = self._readInlineImage(stream)
                    self.operations.append((ii, "INLINE IMAGE"))
                else:
                    self.operations.append((operands, operator))
                    operands = []
            elif peek == '%':
                # If we encounter a comment in the content stream, we have to
                # handle it here.  Typically, readObject will handle
                # encountering a comment -- but readObject assumes that
                # following the comment must be the object we're trying to
                # read.  In this case, it could be an operator instead.
                while peek not in ('\r', '\n'):
                    peek = stream.read(1)
            else:
                operands.append(readObject(stream, None))

    def _readInlineImage(self, stream):
        # begin reading just after the "BI" - begin image
        # first read the dictionary of settings.
        settings = DictionaryObject()
        while True:
            tok = readNonWhitespace(stream)
            stream.seek(-1, 1)
            if tok == "I":
                # "ID" - begin of image data
                break
            key = readObject(stream, self.pdf)
            tok = readNonWhitespace(stream)
            stream.seek(-1, 1)
            value = readObject(stream, self.pdf)
            settings[key] = value
        # left at beginning of ID
        tmp = stream.read(3)
        assert tmp[:2] == "ID"
        data = ""
        while True:
            tok = stream.read(1)
            if tok == "E":
                next = stream.read(1)
                if next == "I":
                    break
                else:
                    stream.seek(-1, 1)
                    data += tok
            else:
                data += tok
        readNonWhitespace(stream)
        stream.seek(-1, 1)
        return {"settings": settings, "data": data}

    def _getData(self):
        newdata = StringIO()
        for operands, operator in self.operations:
            if operator == "INLINE IMAGE":
                newdata.write("BI")
                dicttext = StringIO()
                operands["settings"].writeToStream(dicttext, None)
                newdata.write(dicttext.getvalue()[2:-2])
                newdata.write("ID ")
                newdata.write(operands["data"])
                newdata.write("EI")
            else:
                for op in operands:
                    op.writeToStream(newdata, None)
                    newdata.write(" ")
                newdata.write(operator)
            newdata.write("\n")
        return newdata.getvalue()

    def _setData(self, value):
        self.__parseContentStream(StringIO(value))

    _data = property(_getData, _setData)


##
# This class represents a single page within a PDF file.  Typically this object
# will be created by accessing the {@link #PdfFileReader.getPage getPage}
# function of the {@link #PdfFileReader PdfFileReader} class, but it is
# also possible to create an empty page with the createBlankPage static
# method.
# @param pdf PDF file the page belongs to (optional, defaults to None).
class PageObject(DictionaryObject):
    def __init__(self, pdf=None, indirectRef=None):
        DictionaryObject.__init__(self)
        self.pdf = pdf
        # Stores the original indirect reference
        # to this object in its source PDF
        self.indirectRef = indirectRef

    ##
    # Returns a new blank page.
    # If width or height is None, try to get the page size from the
    # last page of pdf. If pdf is None or contains no page, a
    # PageSizeNotDefinedError is raised.
    # @param pdf    PDF file the page belongs to
    # @param width  The width of the new page expressed in default user
    #               space units.
    # @param height The height of the new page expressed in default user
    #               space units.
    def createBlankPage(pdf=None, width=None, height=None):
        page = PageObject(pdf)

        # Creates a new page (cf PDF Reference  7.7.3.3)
        page.__setitem__(NameObject('/Type'), NameObject('/Page'))
        page.__setitem__(NameObject('/Parent'), NullObject())
        page.__setitem__(NameObject('/Resources'), DictionaryObject())
        if width is None or height is None:
            if pdf is not None and pdf.getNumPages() > 0:
                lastpage = pdf.getPage(pdf.getNumPages() - 1)
                width = lastpage.mediaBox.getWidth()
                height = lastpage.mediaBox.getHeight()
            else:
                raise utils.PageSizeNotDefinedError()
        page.__setitem__(NameObject('/MediaBox'),
                         RectangleObject([0, 0, width, height]))

        return page
    createBlankPage = staticmethod(createBlankPage)

    ##
    # Rotates a page clockwise by increments of 90 degrees.
    # <p>
    # Stability: Added in v1.1, will exist for all future v1.x releases.
    # @param angle Angle to rotate the page.  Must be an increment of 90 deg.
    def rotateClockwise(self, angle):
        assert angle % 90 == 0
        self._rotate(angle)
        return self

    ##
    # Rotates a page counter-clockwise by increments of 90 degrees.
    # <p>
    # Stability: Added in v1.1, will exist for all future v1.x releases.
    # @param angle Angle to rotate the page.  Must be an increment of 90 deg.
    def rotateCounterClockwise(self, angle):
        assert angle % 90 == 0
        self._rotate(-angle)
        return self

    def _rotate(self, angle):
        currentAngle = self.get("/Rotate", 0)
        self[NameObject("/Rotate")] = NumberObject(currentAngle + angle)

    def _mergeResources(res1, res2, resource):
        newRes = DictionaryObject()
        newRes.update(res1.get(resource, DictionaryObject()).getObject())
        page2Res = res2.get(resource, DictionaryObject()).getObject()
        renameRes = {}
        for key in page2Res.keys():
            if key in newRes and newRes[key] != page2Res[key]:
                newname = NameObject(key + "renamed")
                renameRes[key] = newname
                newRes[newname] = page2Res[key]
            elif key not in newRes:
                newRes[key] = page2Res.raw_get(key)
        return newRes, renameRes
    _mergeResources = staticmethod(_mergeResources)

    def _contentStreamRename(stream, rename, pdf):
        if not rename:
            return stream
        stream = ContentStream(stream, pdf)
        for operands, operator in stream.operations:
            for i in range(len(operands)):
                op = operands[i]
                if isinstance(op, NameObject):
                    operands[i] = rename.get(op, op)
        return stream
    _contentStreamRename = staticmethod(_contentStreamRename)

    def _pushPopGS(contents, pdf):
        # adds a graphics state "push" and "pop" to the beginning and end
        # of a content stream.  This isolates it from changes such as
        # transformation matricies.
        stream = ContentStream(contents, pdf)
        stream.operations.insert(0, [[], "q"])
        stream.operations.append([[], "Q"])
        return stream
    _pushPopGS = staticmethod(_pushPopGS)

    def _addTransformationMatrix(contents, pdf, ctm):
        # adds transformation matrix at the beginning of the given
        # contents stream.
        a, b, c, d, e, f = ctm
        contents = ContentStream(contents, pdf)
        contents.operations.insert(0, [[FloatObject(a), FloatObject(b),
                                        FloatObject(c), FloatObject(d),
                                        FloatObject(e), FloatObject(f)],
                                   " cm"])
        return contents
    _addTransformationMatrix = staticmethod(_addTransformationMatrix)

    ##
    # Returns the /Contents object, or None if it doesn't exist.
    # /Contents is optionnal, as described in PDF Reference  7.7.3.3
    def getContents(self):
        if "/Contents" in self:
            return self["/Contents"].getObject()
        else:
            return None

    ##
    # Merges the content streams of two pages into one.  Resource references
    # (i.e. fonts) are maintained from both pages.  The mediabox/cropbox/etc
    # of this page are not altered.  The parameter page's content stream will
    # be added to the end of this page's content stream, meaning that it will
    # be drawn after, or "on top" of this page.
    # <p>
    # Stability: Added in v1.4, will exist for all future 1.x releases.
    # @param page2 An instance of {@link #PageObject PageObject} to be merged
    #              into this one.
    def mergePage(self, page2):
        self._mergePage(page2)

    ##
    # Actually merges the content streams of two pages into one. Resource
    # references (i.e. fonts) are maintained from both pages. The
    # mediabox/cropbox/etc of this page are not altered. The parameter page's
    # content stream will be added to the end of this page's content stream,
    # meaning that it will be drawn after, or "on top" of this page.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged
    #              into this one.
    # @param page2transformation A function which applies a transformation to
    #                            the content stream of page2. Takes: page2
    #                            contents stream. Must return: new contents
    #                            stream. If omitted, the content stream will
    #                            not be modified.
    # @param ctm A 6-item list containing the content transformation matrix.
    #            Although this list could be pulled from the closure of the
    #            page2transformation function, it is simpler and more
    #            extensible to have it as a separate parameter.
    # @param expand Whether the page should be expanded to fit the dimensions
    #               of the page to be merged
    def _mergePage(self, page2, page2transformation=None,
                   ctm=None, expand=False):
        # First we work on merging the resource dictionaries.  This allows us
        # to find out what symbols in the content streams we might need to
        # rename.
        newResources = DictionaryObject()
        rename = {}
        originalResources = self["/Resources"].getObject()
        page2Resources = page2["/Resources"].getObject()

        for res in ["/ExtGState", "/Font", "/XObject", "/ColorSpace",
                    "/Pattern", "/Shading", "/Properties"]:
            new, newrename = PageObject._mergeResources(originalResources,
                                                        page2Resources, res)
            if new:
                newResources[NameObject(res)] = new
                rename.update(newrename)
        # Combine /ProcSet sets.
        newResources[NameObject("/ProcSet")] = ArrayObject(
            frozenset(originalResources.get(
                "/ProcSet", ArrayObject()).getObject()).union(
                    frozenset(page2Resources.get(
                        "/ProcSet", ArrayObject()).getObject())))
        newContentArray = ArrayObject()
        originalContent = self.getContents()
        if originalContent is not None:
            newContentArray.append(PageObject._pushPopGS(
                originalContent, self.pdf))
        page2Content = page2.getContents()
        if page2Content is not None:
            if page2transformation is not None:
                page2Content = page2transformation(page2Content)
            page2Content = PageObject._contentStreamRename(
                page2Content, rename, self.pdf)
            page2Content = PageObject._pushPopGS(page2Content, self.pdf)
            newContentArray.append(page2Content)
        # if expanding the page to fit a new page,
        # calculate the new media box size
        if expand:
            corners1 = [self.mediaBox.getLowerLeft_x().as_numeric(),
                        self.mediaBox.getLowerLeft_y().as_numeric(),
                        self.mediaBox.getUpperRight_x().as_numeric(),
                        self.mediaBox.getUpperRight_y().as_numeric()]
            corners2 = [page2.mediaBox.getLowerLeft_x().as_numeric(),
                        page2.mediaBox.getLowerLeft_y().as_numeric(),
                        page2.mediaBox.getUpperLeft_x().as_numeric(),
                        page2.mediaBox.getUpperLeft_y().as_numeric(),
                        page2.mediaBox.getUpperRight_x().as_numeric(),
                        page2.mediaBox.getUpperRight_y().as_numeric(),
                        page2.mediaBox.getLowerRight_x().as_numeric(),
                        page2.mediaBox.getLowerRight_y().as_numeric()]
            if ctm is not None:
                new_x = map(lambda i: ctm[0]*corners2[i]
                            + ctm[2]*corners2[i+1] + ctm[4],
                            range(0, 8, 2))
                new_y = map(lambda i: ctm[1]*corners2[i]
                            + ctm[3]*corners2[i+1] + ctm[5],
                            range(0, 8, 2))
            else:
                new_x = corners2[0:8:2]
                new_y = corners2[1:8:2]
            lowerleft = [min(new_x), min(new_y)]
            upperright = [max(new_x), max(new_y)]
            lowerleft = [min(corners1[0], lowerleft[0]),
                         min(corners1[1], lowerleft[1])]
            upperright = [max(corners1[2], upperright[0]),
                          max(corners1[3], upperright[1])]

            self.mediaBox.setLowerLeft(lowerleft)
            self.mediaBox.setUpperRight(upperright)

        self[NameObject('/Contents')] = ContentStream(
            newContentArray, self.pdf)
        self[NameObject('/Resources')] = newResources

    ##
    # This is similar to mergePage, but a transformation matrix is
    # applied to the merged stream.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged.
    # @param ctm   A 6 elements tuple containing the operands of the
    #              transformation matrix
    def mergeTransformedPage(self, page2, ctm):
        self._mergePage(page2, lambda page2Content:
                        PageObject._addTransformationMatrix(
                            page2Content, page2.pdf, ctm), ctm)

    ##
    # This is similar to mergePage, but the stream to be merged is scaled
    # by appling a transformation matrix.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged.
    # @param factor The scaling factor
    def mergeScaledPage(self, page2, factor):
        # CTM to scale : [ sx 0 0 sy 0 0 ]
        return self.mergeTransformedPage(page2, [factor, 0,
                                                 0,      factor,
                                                 0,      0])

    ##
    # This is similar to mergePage, but the stream to be merged is rotated
    # by appling a transformation matrix.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged.
    # @param rotation The angle of the rotation, in degrees
    def mergeRotatedPage(self, page2, rotation):
        rotation = math.radians(rotation)
        return self.mergeTransformedPage(page2, [math.cos(rotation),
                                                 math.sin(rotation),
                                                 -math.sin(rotation),
                                                 math.cos(rotation),
                                                 0, 0])

    ##
    # This is similar to mergePage, but the stream to be merged is translated
    # by appling a transformation matrix.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged.
    # @param tx    The translation on X axis
    # @param tx    The translation on Y axis
    def mergeTranslatedPage(self, page2, tx, ty):
        return self.mergeTransformedPage(page2, [1,  0,
                                                 0,  1,
                                                 tx, ty])

    ##
    # This is similar to mergePage, but the stream to be merged is rotated
    # and scaled by appling a transformation matrix.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged.
    # @param rotation The angle of the rotation, in degrees
    # @param factor The scaling factor
    def mergeRotatedScaledPage(self, page2, rotation, scale):
        rotation = math.radians(rotation)
        rotating = [[math.cos(rotation), math.sin(rotation), 0],
                    [-math.sin(rotation), math.cos(rotation), 0],
                    [0, 0, 1]]
        scaling = [[scale, 0, 0],
                   [0, scale, 0],
                   [0, 0, 1]]
        ctm = utils.matrixMultiply(rotating, scaling)

        return self.mergeTransformedPage(page2,
                                         [ctm[0][0], ctm[0][1],
                                          ctm[1][0], ctm[1][1],
                                          ctm[2][0], ctm[2][1]])

    ##
    # This is similar to mergePage, but the stream to be merged is translated
    # and scaled by appling a transformation matrix.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged.
    # @param scale The scaling factor
    # @param tx    The translation on X axis
    # @param tx    The translation on Y axis
    def mergeScaledTranslatedPage(self, page2, scale, tx, ty):
        translation = [[1, 0, 0],
                       [0, 1, 0],
                       [tx, ty, 1]]
        scaling = [[scale, 0, 0],
                   [0, scale, 0],
                   [0, 0, 1]]
        ctm = utils.matrixMultiply(scaling, translation)

        return self.mergeTransformedPage(page2, [ctm[0][0], ctm[0][1],
                                                 ctm[1][0], ctm[1][1],
                                                 ctm[2][0], ctm[2][1]])

    ##
    # This is similar to mergePage, but the stream to be merged is translated,
    # rotated and scaled by appling a transformation matrix.
    #
    # @param page2 An instance of {@link #PageObject PageObject} to be merged.
    # @param tx    The translation on X axis
    # @param ty    The translation on Y axis
    # @param rotation The angle of the rotation, in degrees
    # @param scale The scaling factor
    def mergeRotatedScaledTranslatedPage(self, page2, rotation, scale, tx, ty):
        translation = [[1, 0, 0],
                       [0, 1, 0],
                       [tx, ty, 1]]
        rotation = math.radians(rotation)
        rotating = [[math.cos(rotation), math.sin(rotation), 0],
                    [-math.sin(rotation), math.cos(rotation), 0],
                    [0, 0, 1]]
        scaling = [[scale, 0, 0],
                   [0, scale, 0],
                   [0, 0, 1]]
        ctm = utils.matrixMultiply(rotating, scaling)
        ctm = utils.matrixMultiply(ctm, translation)

        return self.mergeTransformedPage(page2, [ctm[0][0], ctm[0][1],
                                                 ctm[1][0], ctm[1][1],
                                                 ctm[2][0], ctm[2][1]])

    ##
    # Applys a transformation matrix the page.
    #
    # @param ctm   A 6 elements tuple containing the operands of the
    #              transformation matrix
    def addTransformation(self, ctm):
        originalContent = self.getContents()
        if originalContent is not None:
            newContent = PageObject._addTransformationMatrix(
                originalContent, self.pdf, ctm)
            newContent = PageObject._pushPopGS(newContent, self.pdf)
            self[NameObject('/Contents')] = newContent

    ##
    # Scales a page by the given factors by appling a transformation
    # matrix to its content and updating the page size.
    #
    # @param sx The scaling factor on horizontal axis
    # @param sy The scaling factor on vertical axis
    def scale(self, sx, sy):
        self.addTransformation([sx, 0,
                                0,  sy,
                                0,  0])
        self.mediaBox = RectangleObject([
            float(self.mediaBox.getLowerLeft_x()) * sx,
            float(self.mediaBox.getLowerLeft_y()) * sy,
            float(self.mediaBox.getUpperRight_x()) * sx,
            float(self.mediaBox.getUpperRight_y()) * sy])

    ##
    # Scales a page by the given factor by appling a transformation
    # matrix to its content and updating the page size.
    #
    # @param factor The scaling factor
    def scaleBy(self, factor):
        self.scale(factor, factor)

    ##
    # Scales a page to the specified dimentions by appling a
    # transformation matrix to its content and updating the page size.
    #
    # @param width The new width
    # @param height The new heigth
    def scaleTo(self, width, height):
        sx = width / (self.mediaBox.getUpperRight_x() -
                      self.mediaBox.getLowerLeft_x())
        sy = height / (self.mediaBox.getUpperRight_y() -
                       self.mediaBox.getLowerLeft_x())
        self.scale(sx, sy)

    ##
    # Compresses the size of this page by joining all content streams and
    # applying a FlateDecode filter.
    # <p>
    # Stability: Added in v1.6, will exist for all future v1.x releases.
    # However, it is possible that this function will perform no action if
    # content stream compression becomes "automatic" for some reason.
    def compressContentStreams(self):
        content = self.getContents()
        if content is not None:
            if not isinstance(content, ContentStream):
                content = ContentStream(content, self.pdf)
            self[NameObject("/Contents")] = content.flateEncode()

    ##
    # Locate all text drawing commands, in the order they are provided in the
    # content stream, and extract the text.  This works well for some PDF
    # files, but poorly for others, depending on the generator used.  This will
    # be refined in the future.  Do not rely on the order of text coming out of
    # this function, as it will change if this function is made more
    # sophisticated.
    # <p>
    # Stability: Added in v1.7, will exist for all future v1.x releases.  May
    # be overhauled to provide more ordered text in the future.
    # @return a unicode string object
    def extractText(self):
        text = u""
        content = self["/Contents"].getObject()
        if not isinstance(content, ContentStream):
            content = ContentStream(content, self.pdf)
        # Note: we check all strings are TextStringObjects.  ByteStringObjects
        # are strings where the byte->string encoding was unknown, so adding
        # them to the text here would be gibberish.
        for operands, operator in content.operations:
            if operator == "Tj":
                _text = operands[0]
                if isinstance(_text, TextStringObject):
                    text += _text
            elif operator == "T*":
                text += "\n"
            elif operator == "'":
                text += "\n"
                _text = operands[0]
                if isinstance(_text, TextStringObject):
                    text += operands[0]
            elif operator == '"':
                _text = operands[2]
                if isinstance(_text, TextStringObject):
                    text += "\n"
                    text += _text
            elif operator == "TJ":
                for i in operands[0]:
                    if isinstance(i, TextStringObject):
                        text += i
        return text

    ##
    # A rectangle (RectangleObject), expressed in default user space units,
    # defining the boundaries of the physical medium on which the page is
    # intended to be displayed or printed.
    # <p>
    # Stability: Added in v1.4, will exist for all future v1.x releases.
    mediaBox = createRectangleAccessor("/MediaBox", ())

    ##
    # A rectangle (RectangleObject), expressed in default user space units,
    # defining the visible region of default user space.  When the page is
    # displayed or printed, its contents are to be clipped (cropped) to this
    # rectangle and then imposed on the output medium in some
    # implementation-defined manner.  Default value: same as MediaBox.
    # <p>
    # Stability: Added in v1.4, will exist for all future v1.x releases.
    cropBox = createRectangleAccessor("/CropBox", ("/MediaBox",))

    ##
    # A rectangle (RectangleObject), expressed in default user space units,
    # defining the region to which the contents of the page should be clipped
    # when output in a production enviroment.
    # <p>
    # Stability: Added in v1.4, will exist for all future v1.x releases.
    bleedBox = createRectangleAccessor("/BleedBox", ("/CropBox", "/MediaBox"))

    ##
    # A rectangle (RectangleObject), expressed in default user space units,
    # defining the intended dimensions of the finished page after trimming.
    # <p>
    # Stability: Added in v1.4, will exist for all future v1.x releases.
    trimBox = createRectangleAccessor("/TrimBox", ("/CropBox", "/MediaBox"))

    ##
    # A rectangle (RectangleObject), expressed in default user space units,
    # defining the extent of the page's meaningful content as intended by the
    # page's creator.
    # <p>
    # Stability: Added in v1.4, will exist for all future v1.x releases.
    artBox = createRectangleAccessor("/ArtBox", ("/CropBox", "/MediaBox"))

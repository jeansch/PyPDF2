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

from generic import DictionaryObject, TextStringObject


##
# A class representing the basic document metadata provided in a PDF File.
# <p>
# As of pyPdf v1.10, all text properties of the document metadata have two
# properties, eg. author and author_raw.  The non-raw property will always
# return a TextStringObject, making it ideal for a case where the metadata is
# being displayed.  The raw property can sometimes return a ByteStringObject,
# if pyPdf was unable to decode the string's text encoding; this requires
# additional safety in the caller and therefore is not as commonly accessed.
class DocumentInformation(DictionaryObject):
    def __init__(self):
        DictionaryObject.__init__(self)

    def getText(self, key):
        retval = self.get(key, None)
        if isinstance(retval, TextStringObject):
            return retval
        return None

    ##
    # Read-only property accessing the document's title.  Added in v1.6, will
    # exist for all future v1.x releases.  Modified in v1.10 to always return a
    # unicode string (TextStringObject).
    # @return A unicode string, or None if the title is not provided.
    title = property(lambda self: self.getText("/Title"))
    title_raw = property(lambda self: self.get("/Title"))

    ##
    # Read-only property accessing the document's author.  Added in v1.6, will
    # exist for all future v1.x releases.  Modified in v1.10 to always return a
    # unicode string (TextStringObject).
    # @return A unicode string, or None if the author is not provided.
    author = property(lambda self: self.getText("/Author"))
    author_raw = property(lambda self: self.get("/Author"))

    ##
    # Read-only property accessing the subject of the document.  Added in v1.6,
    # will exist for all future v1.x releases.  Modified in v1.10 to always
    # return a unicode string (TextStringObject).
    # @return A unicode string, or None if the subject is not provided.
    subject = property(lambda self: self.getText("/Subject"))
    subject_raw = property(lambda self: self.get("/Subject"))

    ##
    # Read-only property accessing the document's creator.  If the document was
    # converted to PDF from another format, the name of the application (for
    # example, OpenOffice) that created the original document from which it was
    # converted.  Added in v1.6, will exist for all future v1.x releases.
    # Modified in v1.10 to always return a unicode string (TextStringObject).
    # @return A unicode string, or None if the creator is not provided.
    creator = property(lambda self: self.getText("/Creator"))
    creator_raw = property(lambda self: self.get("/Creator"))

    ##
    # Read-only property accessing the document's producer.  If the document
    # was converted to PDF from another format, the name of the application
    # (for example, OSX Quartz) that converted it to PDF.  Added in v1.6, will
    # exist for all future v1.x releases.  Modified in v1.10 to always return a
    # unicode string (TextStringObject).
    # @return A unicode string, or None if the producer is not provided.
    producer = property(lambda self: self.getText("/Producer"))
    producer_raw = property(lambda self: self.get("/Producer"))

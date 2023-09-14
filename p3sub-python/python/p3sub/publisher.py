#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#

from collections import namedtuple
from datetime import timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from os import listdir
from os.path import isfile, getmtime
from p3sub.defs import *
from p3sub.utils import *
from threading import Event, Lock, Thread
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen, Request
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class Publisher :
    def __init__( self, listenUri, feedDirectory ) :
        self.theFeedDirectory = PublisherFeedDirectory( feedDirectory )

        ( self.theWsHost, self.theWsPort ) = listenUri.netloc.split( ':', 2 )
        self.theWsPort          = int( self.theWsPort )
        self.theFeedPath        = listenUri.path
        self.theSubscribePath   = self.theFeedPath + '/sub'
        self.theUnsubscribePath = self.theFeedPath + '/unsub'
        self.theSubscriptions   = {} # subId -> { uri, lastTsEnqueued }

        self.theFeedAndSubscriptionsLock = Lock() # avoid concurrent modifications


    def run( self ) :
        """
        Run the publisher command.
        """

        # thread that sends messages out
        self.theSender = PublisherSender( self )
        self.theSender.start()

        # run a web server
        ws = PublisherWebServer( ( self.theWsHost, self.theWsPort ), self )

        # observe the feed directory
        observer = Observer()
        observer.schedule( ObserverEventHandler( self.theFeedDirectory, self ), self.theFeedDirectory.getDirectory(), recursive=False)
        observer.start()

        print( f"INFO: Serving P3Sub feed at http://{ self.theWsHost }:{self.theWsPort}{ self.theFeedPath } -- ^C to stop" )

        try:
            ws.serve_forever()
        except KeyboardInterrupt:
            pass

        observer.stop()
        self.theSender.stop()
        ws.server_close()
        observer.join()
        self.theSender.join()


    def feedRequestReceived( self, handler ) :
        ( path, query ) = decodeRequestPath( handler.path )
        if P3SUB_PAR_TS in query :
            ts = stringToTs( query[P3SUB_PAR_TS] )
        else :
            ts = None

        if ts :
            elWithBeforeAfter = self.theFeedDirectory.elementAtWithBeforeAfter( ts )
        else :
            elWithBeforeAfter = self.theFeedDirectory.currentElementWithBeforeAfter()

        if elWithBeforeAfter is None:
            return "No such element.\n"

        else :
            handler.send_response( 200 )
            handler.send_header( "Content-type", "text/plain" )
            handler.send_header( "link", f'<{ self.theFeedPath }?{ P3SUB_PAR_TS }={ tsToString( elWithBeforeAfter[1].mtime ) }>; rel="{ P3SUB_REL_CANONICAL }"' );
            handler.send_header( "link", f'<{ self.theSubscribePath }>; rel="{ P3SUB_REL_SUBSCRIBE }"' );
            if elWithBeforeAfter[0] is not None :
                handler.send_header( "link", f'<{ self.theFeedPath }?{ P3SUB_PAR_TS }={ tsToString( elWithBeforeAfter[0].mtime ) }>; rel="{ P3SUB_REL_PREV }"' );
            if elWithBeforeAfter[2] is not None :
                handler.send_header( "link", f'<{ self.theFeedPath }?{ P3SUB_PAR_TS }={ tsToString( elWithBeforeAfter[2].mtime ) }>; rel="{ P3SUB_REL_NEXT }"' );
            handler.end_headers()
            with open( elWithBeforeAfter[1].name, 'rb' ) as f :
                for fBlock in iter( partial( f.read, 1024 ), b'' ) :
                    handler.wfile.write( fBlock )
        return None


    def subscribeRequestReceived( self, handler ) :
        postData = formFields( handler )

        if P3SUB_PAR_SUBID not in postData :
            return f'No { P3SUB_PAR_SUBID } in POSTed data for subscribe request'
        subId = postData[P3SUB_PAR_SUBID]
        if type( subId ) is list :
            if len( subId ) > 1 :
                return f'Too many { P3SUB_PAR_SUBID } in POSTed data for subscribe request'
            subId = subId[0]
        if len( subId ) < 32 :
            return f'Parameter { P3SUB_PAR_SUBID } must have a value of at least 32 characters'

        if P3SUB_PAR_CALLBACK not in postData :
            return f'No { P3SUB_PAR_CALLBACK } in POSTed data for subscribe request'
        callback = postData[P3SUB_PAR_CALLBACK]
        if type( callback ) is list :
            if len( callback ) > 1 :
                return f'Too many { P3SUB_PAR_CALLBACK } in POSTed data for subscribe request'
            callback = callback[0]
        callbackUri = urlparse( callback )
        if not callbackUri.scheme:
            return f'Not a valid callback URI: { urlunparse( callback ) }'

        if P3SUB_PAR_TS in postData:
            fromTs = postData[P3SUB_PAR_TS]
            if type( fromTs ) is list :
                if len( fromTs ) > 1 :
                    return f'Too many { P3SUB_PAR_TS } in POSTed data for subscribe request'
                fromTs = fromTs[0]
            fromTs = stringToTs( fromTs )
        else :
            fromTs = datetime.now( timezone.utc )

        self.theFeedAndSubscriptionsLock.acquire()
        self.theSubscriptions[ subId ] = PublisherSubscription( callbackUri, fromTs )
        self.theFeedAndSubscriptionsLock.release()

        self.theSender.triggerPotentialSend()

        handler.send_response( 200 )
        handler.send_header( "Content-type", "text/plain" )
        handler.send_header( "link", f'<{ self.theUnsubscribePath }>; rel="{ P3SUB_REL_UNSUBSCRIBE }"' );
        handler.end_headers()
        handler.wfile.write( bytes( "Subscription successful.\n", "utf-8" ))

        return None


    def unsubscribeRequestReceived( self, handler ) :
        postData = formFields( handler )
        if P3SUB_PAR_SUBID not in postData :
            return f'No { P3SUB_PAR_SUBID } in POSTed data for unsubscribe request'
        subId = postData[P3SUB_PAR_SUBID]
        if type( subId ) is list :
            if len( subId ) > 1 :
                return f'Too many { P3SUB_PAR_SUBID } in POSTed data for subscribe request'
            subId = subId[0]

        if subId in self.theSubscriptions :
            self.theFeedAndSubscriptionsLock.acquire()
            del self.theSubscriptions[ subId ]
            self.theFeedAndSubscriptionsLock.release()

            handler.send_response( 200 )
            handler.send_header( "Content-type", "text/plain" )
            handler.send_header( "link", f'<{ self.theSubscribePath }>; rel="{ P3SUB_REL_SUBSCRIBE }"' );
            handler.end_headers()
            handler.wfile.write( bytes( "Unsubscription successful.\n", "utf-8" ))
            return None

        else :
            return f"No subscription found with { P3SUB_PAR_SUBID }={ subId }.\n"


    def getRequestReceived( self, handler ) :
        ( path, query ) = decodeRequestPath( handler.path )
        if path == self.theFeedPath :
            ret = self.feedRequestReceived( handler )
        else :
            ret = 1
        return ret


    def postRequestReceived( self, handler ) :
        ( path, query ) = decodeRequestPath( handler.path )
        if path == self.theSubscribePath :
            ret = self.subscribeRequestReceived( handler )
        elif path == self.theUnsubscribePath :
            ret = self.unsubscribeRequestReceived( handler )
        else :
            ret = 1
        return ret


    def processQueue( self ) :
        self.theFeedAndSubscriptionsLock.acquire()

        updatedSubscriptions = {}
        for subId in self.theSubscriptions :
            subData = self.theSubscriptions[ subId ]

            ( previous, toSends ) = self.theFeedDirectory.elementsAfterWithBefore( subData.lastSuccessfulTs )
            uri                   = subData.callbackUri

            if toSends :
                for i in range( 0, len( toSends )) :
                    toSend = toSends[i]

                    if self.sendOne( subId, uri, previous.mtime, toSend ) == 0 :
                        updatedSubscriptions[ subId ] = PublisherSubscription( uri, toSend.mtime )
                        previous = toSend
                    else :
                        print( f'INFO: Cannot reach {uri}, skipping this subscriber this round' )
                        break

        for subId in updatedSubscriptions :
            subData = updatedSubscriptions[ subId ]
            self.theSubscriptions[ subId ] = subData

        self.theFeedAndSubscriptionsLock.release()


    def sendOne( self, subId, uri, before, current ) :

        buf = None
        with open( current.name, 'rb' ) as f:
            buf = f.read()

        if buf is None:
            print( f"ERROR: could not read file { current.name }" )
            return 1

        # Need to pack into one line, API can't do better
        linkHeader = f'<{ self.theUnsubscribePath }>; rel="{ P3SUB_REL_UNSUBSCRIBE }"'
        if before :
            linkHeader += f', <{ self.theFeedPath }?{ P3SUB_PAR_TS }={ tsToString( before ) }>; rel="{ P3SUB_REL_PREV }"'

        headers = {
            'content-type'   : 'application/octet-stream',
            'content-length' : len( buf ),
            'link'           : linkHeader
        }
        uriString = urlunparse( uri )
        uriString += f'?{ P3SUB_PAR_TS }={ tsToString( current.mtime ) }'
        uriString += f'&{ P3SUB_PAR_SUBID }={ subId }'

        response = urlopen( Request( uriString, headers=headers, data=buf, method='PUT' ) )
        if response.status == 200 :
            return 0
        else :
            return 1


class PublisherSubscription( namedtuple( 'PublisherSubscription', [ 'callbackUri', 'lastSuccessfulTs' ] )) :
    pass


class PublisherWebServer( HTTPServer ) :
    """
    The default HTTPServer instantiates request handlers entirely without
    context; there is no way of passing in local data. So
    we override the internal factory method.
    """
    def __init__( self, server_address, publisher, bind_and_activate=True ):
        HTTPServer.__init__( self, server_address, PublisherRequestHandler, bind_and_activate )

        self.thePublisher = publisher


class PublisherRequestHandler( BaseHTTPRequestHandler ) :
    def do_GET( self ):
        try :
            self.complete( self.server.thePublisher.getRequestReceived( self ))
        except BaseException as ex:
            self.complete( 'An internal error occurred: ' + str( ex ))
            raise


    def do_POST( self ):
        try :
            self.complete( self.server.thePublisher.postRequestReceived( self ))
        except BaseException as ex:
            self.complete( 'An internal error occurred: ' + str( ex ))
            raise


    def complete( self, err ) :
        if err :
            self.send_response( 400 )
            self.send_header( "Content-type", "text/plain" )
            self.end_headers()
            self.wfile.write( bytes( f"ERROR: Cannot serve this request.\n{ err }\n", "utf-8" ))



class PublisherFeedDirectory :
    def __init__( self, directory ) :
        self.theDirectory          = directory;
        self.theElementsInSequence = None


    def getDirectory( self ) :
        return self.theDirectory


    def currentElementWithBeforeAfter( self ) :
        self.ensureElementsInSequence()
        if len( self.theElementsInSequence ) > 1 :
            return ( self.theElementsInSequence[-2], self.theElementsInSequence[-1], None )

        elif( len( self.theElementsInSequence ) > 0 ) :
            return ( None, self.theElementsInSequence[-1], None )

        else :
            return None


    def elementAtWithBeforeAfter( self, ts ) :
        self.ensureElementsInSequence()
        # We need to search, as ts may not be exact
        length = len( self.theElementsInSequence )
        for i in range( length-1, -1, -1 ) :
            el = self.theElementsInSequence[i]
            if el.mtime <= ts :
                if i>0 :
                    if i<length-1 :
                        return ( self.theElementsInSequence[i-1], el, self.theElementsInSequence[i+1] )
                    else :
                        return ( self.theElementsInSequence[i-1], el, None )
                else :
                    if i<length-1 :
                        return ( None, el, self.theElementsInSequence[i+1] )
                    else :
                        return ( None, el, None )

        return None


    def elementsAfterWithBefore( self, ts ) :
        self.ensureElementsInSequence()
        for i in range( 0, len( self.theElementsInSequence )) :
            el = self.theElementsInSequence[i]
            if el.mtime <= ts :
                continue

            if i>0 :
                return ( self.theElementsInSequence[i-1], self.theElementsInSequence[i:] )
            else :
                return ( None, self.theElementsInSequence[i:] )
        return ( None, None )


    def ensureElementsInSequence( self ) :
        if self.theElementsInSequence is None :
            files              = listdir( self.theDirectory )
            elementsInSequence = []

            for f in files :
                realF = self.theDirectory + '/' + f
                if not isfile( realF ) :
                    continue

                elementsInSequence.append( PublisherFeedDirectoryElement( name=realF, mtime=datetime.fromtimestamp( getmtime( realF ), timezone.utc )))

            elementsInSequence = sorted( elementsInSequence, key = lambda e : e.mtime )
            self.theElementsInSequence = elementsInSequence

        return self.theElementsInSequence


    def purgeElementsInSequence( self ) :
        self.theElementsInSequence = None


class PublisherFeedDirectoryElement( namedtuple( 'PublisherFeedDirectoryElement', [ 'name', 'mtime' ])) :
    def __str__( self ) :
        return f"PublisherFeedDirectoryElement( name={ self.name }, mtime={ self.mtime } )"


class ObserverEventHandler( FileSystemEventHandler ) :
    def __init__( self, feedDirectory, publisher ) :
        super().__init__()
        self.theFeedDirectory = feedDirectory
        self.thePublisher     = publisher


    def on_any_event( self, event ) :
        # We take the easy way out
        self.thePublisher.theFeedAndSubscriptionsLock.acquire()
        self.theFeedDirectory.purgeElementsInSequence()
        self.thePublisher.theFeedAndSubscriptionsLock.release()

        self.thePublisher.theSender.triggerPotentialSend()


class PublisherSender( Thread ) :
    def __init__( self, publisher ) :
        super().__init__()

        self.thePublisher = publisher
        self.theEvent     = Event()
        self.theActive    = False


    def triggerPotentialSend( self ) :
        self.theEvent.set()


    def run( self ) :
        self.theActive = True
        while self.theActive :
            self.theEvent.wait()
            self.thePublisher.processQueue()
            self.theEvent.clear()


    def stop( self ) :
        self.theActive = False
        self.theEvent.set()


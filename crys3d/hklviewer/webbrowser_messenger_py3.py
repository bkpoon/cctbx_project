from __future__ import absolute_import, division, print_function
import traceback
from libtbx.utils import to_str
import threading, sys
import time

import struct
import asyncio
from websockets.asyncio import server
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

class MyWebSocketServerConnection(server.ServerConnection):
  def __init__(self, *args, **kwargs):
    self.client_connected = None
    self.onlostconnect = None
    super().__init__(*args, **kwargs)
  def connection_made(self, transport) -> None:
    #print("In connection_made()")
    super().connection_made(transport)
    self.client_connected = self.local_address
  def connection_lost(self, exc) -> None:
    #print("In connection_lost()")
    self.client_connected = None
    # close_code and close_reason are only defined once the base class has closed the connection
    super().connection_lost(exc)
    if self.onlostconnect:
      self.onlostconnect(self.client_connected, self.close_code, self.close_reason)

lock_timeout = 2

class WBmessenger(object):
  def __init__(self, viewerparent ):
    try:
      self.parent = viewerparent
      self.ProcessBrowserMessage = self.parent.ProcessBrowserMessage
      self.on_browser_connection = self.parent.on_browser_connection
      self.websockport = self.parent.websockport
      self.sleeptime = self.parent.sleeptime
      self.mprint = self.parent.mprint
      self.parent.lastviewmtrx
      self.browserisopen = False
      self.msgqueue = []
      self.clientmsgqueue = []
      self.replace_msg_lst = []
      self.msgdelim = ":\n"
      self.ishandling = False
      self.websockclient = None
      self.isterminating = False
      self.was_disconnected = None
      self.mywebsock = None
      self.server = None
      self.websockeventloop = None
      self.clientmsgqueue_sem = threading.Semaphore()
      self.listening_sem = threading.Semaphore()
      self.listening_sem.acquire(blocking=True, timeout=lock_timeout)
      self.mprint("WBmessenger got listening_sem", verbose="threadingmsg")
    except Exception as e:
      print( to_str(e) + "\n" + traceback.format_exc(limit=10))


  async def start_server(self):
    # websockets.asyncio.server.serve() must be called from within the running event loop
    self.server = await server.serve(self.WebSockHandler, 'localhost',
                                      self.websockport, #ssl=ssl_context,
                                      create_connection=MyWebSocketServerConnection,
                                      max_size=100000000, # allow for saving 100Mb size images
                                      )


  def start_server_loop(self):
    #time.sleep(10)
    self.mprint("HKLviewerWebSockServerThread started", verbose=1)
    self.websockeventloop.run_until_complete(self.start_server())
    self.mprint("websocket server is listening", verbose=1)
    self.listening_sem.release()
    self.mprint("WBmessenger released listening_sem", verbose="threadingmsg")
    self.websockeventloop.run_forever()
    self.mprint("websockeventloop has run forever", verbose=1)


  def StartWebsocket(self):
    try:
      if self.websockeventloop is not None:
        self.mprint("websockeventloop already running", verbose=1)
        return
      if self.websockeventloop is None:
        self.websockeventloop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.websockeventloop)
        if self.parent.debug is not None:
          self.websockeventloop.set_debug(True)
          import logging
          logger = logging.getLogger("websockets.server")
          logger.setLevel(logging.DEBUG)
          logger.addHandler(logging.StreamHandler())

      self.mprint("Starting websocket server on port %s" %str(self.websockport), verbose=1)
      # run_forever() blocks execution so put in a separate thread
      self.wst = threading.Thread(target=self.start_server_loop, name="HKLviewerWebSockServerThread" )
      self.wst.daemon = True # ensure thread dies whenever program terminates through sys.exit()
      self.wst.start()
      self.websocketclientmsgthrd = threading.Thread(target = self.ProcessClientMessageLoop,
                                                     name="WebsocketClientMessageThread")
      self.websocketclientmsgthrd.daemon = True # ensure thread dies whenever program terminates through sys.exit()
      self.websocketclientmsgthrd.start()
    except Exception as e:
      self.mprint( to_str(e) + "\n" + traceback.format_exc(limit=10), verbose=0)


  def StopWebsocket(self):
    self.isterminating = True
    self.javascriptcleaned = True
    self.mprint("Shutting down websockeventloop", verbose=1)
    self.websockeventloop.stop()


  async def WebSockHandler(self, mywebsock):
    # invoked only when a new websocket client (the browser) is waiting to connect
    self.mprint("Pending websocket client wanting to connect", verbose=1)
    if self.mywebsock is not None and self.mywebsock.state == State.CLOSING \
                                  and self.websockclient is not None:
      await self.mywebsock.wait_closed()
    if self.websockclient is not None or self.ishandling:
      await asyncio.sleep(0.5)
      return
    self.ishandling = True
    self.OnConnectWebsocketClient(mywebsock.client_connected)
    mywebsock.onlostconnect = self.OnLostConnectWebsocketClient
    self.mywebsock = mywebsock
    getmsgtask = asyncio.ensure_future(self.ReceiveMsgQueue())
    sendmsgtask = asyncio.ensure_future(self.SendMsgQueue())
    done, pending = await asyncio.wait( [getmsgtask, sendmsgtask],
      return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
      task.cancel()
    self.mprint("Exiting WebSockHandler", verbose=1)
    self.ishandling = False


  async def ReceiveMsgQueue(self):
    while True:
      await asyncio.sleep(self.sleeptime)
      if self.was_disconnected in [4242, # reload
                                    4241, # javascriptcleanup
                                    1006, # WebSocketServerProtocol.close_code is absent
                                    1001, # normal exit
                                    1005,
                                    1000
                                    ]:
        await self.mywebsock.wait_closed()
        self.mprint("ReceiveMsgQueue shutdown", verbose=1)
        return # shutdown
      if self.websockclient is None or self.mywebsock.client_connected is None:
        await asyncio.sleep(self.sleeptime)
        continue
      message = ""
      try: # use EAFP rather than LBYL style with websockets
        message = await self.mywebsock.recv()
      except Exception as e:
        self.OnConnectionClosedException(e)
        if self.was_disconnected != 4242:
          self.mprint( to_str(e) + "\n" + traceback.format_exc(limit=10), verbose=1)
      self.clientmsgqueue_sem.acquire(blocking=True, timeout=lock_timeout)
      # Avoid overwhelming ProcessBrowserMessage() with too many messages of the same kind (like tooltips)
      # as it will uncontrolably grow clientmsgqueue which will slow down or make HKLviewer unresponsive
      # when displaying tooltips of a big dataset.
      # Instead we check if the substring rmsg matches the current message. If so and if it is already
      # present in clientmsgqueue, then replace it with message rather than appending it to clientmsgqueue.
      notfound = True
      for rmsg in self.replace_msg_lst:
        if isinstance(message, str) and rmsg in message:
          for msg in self.clientmsgqueue:
            if rmsg in msg:
              msg = message
              notfound = False
              break
      if notfound:
        self.clientmsgqueue.append(message)
      self.clientmsgqueue_sem.release()


  async def SendMsgQueue(self):
    while True:
      try:
        nwait = 0.0
        await asyncio.sleep(self.sleeptime)
        if self.was_disconnected in [4242, # reload
                                      4241, # javascriptcleanup
                                      1006, # WebSocketServerProtocol.close_code is absent
                                      1001, # normal exit
                                      1005,
                                      1000
                                      ]:
          self.mprint("SendMsgQueue shutdown", verbose=1)
          return # shutdown
        if self.parent.javascriptcleaned or self.was_disconnected == 4241: # or self.was_disconnected == 1001:
          return
        if len(self.msgqueue):
          pendingmessagetype, pendingmessage, pendingbinary = self.msgqueue[0]
          gotsent = await self.send_msg_to_browser(pendingmessagetype, pendingmessage, pendingbinary)
          while not self.browserisopen:  #self.websockclient:
            await asyncio.sleep(self.sleeptime)
            nwait += self.sleeptime
            if nwait > self.parent.handshakewait or self.parent.javascriptcleaned \
                or not self.parent.params.viewer.scene_id is not None:
              continue
          if gotsent:
            self.msgqueue.remove( self.msgqueue[0] )
      except Exception as e:
        self.mprint( str(e) + traceback.format_exc(limit=10), verbose=0)


  def ProcessClientMessageLoop(self):
    while self.isterminating == False:
      if len(self.clientmsgqueue):
        self.clientmsgqueue_sem.acquire(blocking=True, timeout=lock_timeout)
        pendingmessage = self.clientmsgqueue[0]
        self.ProcessBrowserMessage(pendingmessage)
        self.clientmsgqueue.remove( self.clientmsgqueue[0] )
        self.clientmsgqueue_sem.release()
      time.sleep(self.sleeptime)
    self.mprint("Shutting down WebsocketClientMessageThread", verbose=1)


  def AddToBrowserMsgQueue(self, msgtype, msg="",binary=False):
    self.msgqueue.append( (msgtype, msg, binary) )


  def OnConnectWebsocketClient(self, client):
    self.websockclient = client
    self.mprint( "Browser connected " + str( self.websockclient ), verbose=1 )
    self.on_browser_connection()
    self.was_disconnected = None
    if self.parent.lastviewmtrx and self.parent.params.viewer.scene_id is not None:
      self.parent.set_volatile_params()
      self.mprint( "Reorienting client after refresh:" + str( self.websockclient ), verbose=2 )
      self.AddToBrowserMsgQueue("ReOrient", self.parent.lastviewmtrx)


  def OnLostConnectWebsocketClient(self, client, close_code, close_reason):
    msg =  "Browser lost connection %s, code %s, reason: %s" %(str(self.websockclient), close_code, close_reason)
    self.mprint(msg , verbose=1 )
    self.was_disconnected = close_code
    self.browserisopen = False
    self.websockclient = None
    self.ishandling = False


  def OnConnectionClosedException(self, e):
    # recv() and send() raise ConnectionClosed once the browser has disconnected
    if isinstance(e, ConnectionClosed):
      if e.rcvd is not None:
        self.OnDisconnectWebsocketClient(None, e.rcvd.code, e.rcvd.reason)
      else: # no close frame received from the browser
        self.OnDisconnectWebsocketClient(None, 1006, "")


  def OnDisconnectWebsocketClient(self, client, close_code, close_reason):
    msg =  "Browser disconnected %s, code %s, reason: %s" %(str(self.websockclient), close_code, close_reason)
    self.mprint(msg , verbose=1 )
    self.was_disconnected = close_code
    self.websockclient = None
    self.ishandling = False


  async def send_msg_to_browser(self, msgtype, msg="", binary=False):
    message = u"" + msgtype + self.msgdelim + str(msg)
    nwait = 0.0
    while isinstance(self.parent.lastmsg, str) and \
      not ("Ready" in self.parent.lastmsg or "tooltip_id" in self.parent.lastmsg \
      or "CurrentViewOrientation" in self.parent.lastmsg or "AutoViewSet" in self.parent.lastmsg \
      or "ReOrient" in self.parent.lastmsg or "JavaScriptCleanUp" in self.parent.lastmsg ) \
      or self.websockclient is None:
      await asyncio.sleep(self.sleeptime)
      nwait += self.sleeptime
      if self.was_disconnected != None:
        return False
      if nwait > 200 and self.browserisopen:
        self.mprint("ERROR: No handshake from browser!", verbose=0 )
        self.mprint("failed sending " + msgtype, verbose=1)
        self.was_disconnected = 1005
        #break
        return False
    if self.browserisopen and self.websockclient is not None or self.mywebsock.client_connected is not None:
      try: # use EAFP rather than LBYL style with websockets
        if not binary:
          await self.mywebsock.send( message )
        else:
          # Binary data is sent as a pair of messages. First a plain string containing the message type
          # is sent. Then the actual data array is sent in binary format as a bytearray.
          # When HKLjavascripts notes the second message is in binary format it pairs it up with the
          # previous message which is the message type so it can be processed
          await self.mywebsock.send( msgtype )
          byteslst = struct.pack("%sf" % len(msg), *msg)
          await self.mywebsock.send( bytearray(byteslst) )
        return True
      except Exception as e:
        self.OnConnectionClosedException(e)
        if self.was_disconnected != 4242:
          self.mprint( str(e) + "\n" + traceback.format_exc(limit=10), verbose=1)
        self.websockclient = None
        return False
    else:
      return False

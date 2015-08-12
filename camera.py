from Queue import Queue
import json, socket, threading, time, select, os
from os.path import basename, getsize

class Camera():
  def __init__(self, ip="192.168.42.1", port=7878):
    self.ip = ip
    self.port = port
    self.socketopen = -1
    self.qsend = Queue()
    self.token = 0
    self.recv = ""
    self.link = False
    self.jsonon = False
    self.jsonoff = 0
    self.msgbusy = 0
    self.cambusy = False
    self.showtime = True
    self.status = {}
    self.filetaken = ""
    self.recording = False
    self.rectime = "00:00:00"
    self.settings = ""
    self.taken = threading.Event()
    self.quit = threading.Event()
    self.wifioff = threading.Event()
    self.lsdir = threading.Event()
    self.dlstart = threading.Event()
    self.dlcomplete = threading.Event()
    self.dlstop = threading.Event()
    self.dlerror = threading.Event()
    
  def __str__(self):
    info = dict()
    info["ip"] = self.ip
    info["port"] = self.port
    info["link"] = self.link
    return str(info)

  def LinkCamera(self):
    self.socketopen = -1
    self.qsend = Queue()
    self.token = 0
    self.recv = ""
    self.link = False
    #self.wifi = True
    self.taken.clear()
    self.wifioff.clear()
    self.lsdir.clear()
    self.dlstart.clear()
    self.dlcomplete.clear()
    self.dlstop.clear()
    self.dlerror.clear()
    self.jsonon = False
    self.jsonoff = 0
    self.msgbusy = 0
    self.cambusy = False
    self.showtime = True
    self.status = {}
    self.filetaken = ""
    self.recording = False
    self.rectime = "00:00:00"
    self.settings = ""
    threading.Thread(target=self.ThreadSend, name="ThreadSend").start()
#     self.tsend= threading.Thread(target=self.ThreadSend)
#     self.tsend.setDaemon(True)
#     self.tsend.setName('ThreadSend')
#     self.tsend.start()
    threading.Thread(target=self.ThreadRecv, name="ThreadRecv").start()
#     self.trecv= threading.Thread(target=self.ThreadRecv)
#     self.trecv.setDaemon(True)
#     self.trecv.setName('ThreadRecv')
#     self.trecv.start()

  def UnlinkCamera(self):
    if self.link:
      self.SendMsg('{"msg_id":258}')
    else:
      self.Disconnect()

  def SendMsg(self, msg):
    self.qsend.put(msg)

  def ThreadSend(self):
    i = 0
    #print "ThreadSend Starts\n"
    if self.socketopen <> 0:
      while self.socketopen <> 0 and i < 4:
        i += 1
        print "try to connect socket %d" %i
        self.Connect()
      if self.socketopen <> 0:
        self.quit.set()
        self.taken.set()
        print "socket time out"
        return
    print "socket connected"
    if self.socketopen == 0:
      #print "wait for token from camera"
      while not self.link:
        if self.quit.isSet():
          break
      #print "start sending loop"
      while self.socketopen == 0:
        if self.quit.isSet():
          break
        if self.msgbusy == 0:
          data = json.loads(self.qsend.get())
          allowsendout = True
          if data["msg_id"] == 515 and not self.recording:
            allowsendout = False
          if allowsendout:
            data["token"] = self.token
            print "sent out:", json.dumps(data, indent=2)
            self.msgbusy = data["msg_id"]
            self.srv.send(json.dumps(data))

  def JsonHandle(self, data):
    print "received:", json.dumps(data, indent=2)
    # confirm message: rval = 0
    if data.has_key("rval"):
      self.JsonRval(data)
    # status message: msg_id = 7
    elif data["msg_id"] == 7:
      self.JsonStatus(data)
      #print "camera status:", json.dumps(self.status, indent=2)

  # status message: 7
  def JsonStatus(self, data):
    #if "param" in data.keys():
    if data.has_key("param"):
      if data["type"] == "battery":
        self.status["battery"] = data["param"]
        self.status["adapter_status"] = "0"
      elif data["type"] == "adapter":
        self.status["battery"] = data["param"]
        self.status["adapter_status"] = "1"
      #elif data["type"] == "start_photo_capture":
        #self.cambusy = True
      elif data["type"] == "photo_taken":
        self.cambusy = False
        self.status[data["type"]] = data["param"]
        self.filetaken = data["param"].replace("/tmp/fuse_d/DCIM","")
        #print self.filetaken
        self.taken.set()
      elif data["type"] == "video_record_complete":
        self.cambusy = False
        self.status[data["type"]] = data["param"]
        self.filetaken = data["param"].replace("/tmp/fuse_d/DCIM","")
        print self.filetaken
        self.taken.set()
      elif data["type"] == "get_file_complete":
        self.dlcomplete.set()
      elif data["type"] == "get_file_fail":
        self.status["offset"] = data["param"]
        self.dlerror.set()
        #self.StartDownload(self.status["file"], self.status["size"], self.status["offset"])
        #threading.Thread(target=self.ThreadDownload, args=(self.status["file"],self.status["size"],self.status["offset"],),name="ThreadDownload").start()
        #self.SendMsg('{"msg_id": 1285,"fetch_size":%d,"param": "%s", "offset": %d}'%(self.status["size"],self.status["file"],data["param"]))
      else:
        self.status[data["type"]] = data["param"]
    else:
      if data["type"] == "start_video_record":
        self.cambusy = False
        self.recording = True
        if self.showtime:
          self.SendMsg('{"msg_id":515}')
      elif data["type"] == "piv_complete":
        self.cambusy = False
        self.filetaken = "piv_complete"
        self.taken.set()
      elif data["type"] == "wifi_will_shutdown":
        self.wifioff.set()
        self.link = False
        self.UnlinkCamera()

  '''
  normal rval = 0
  other rval:
   -4: token lost
   -9: msg 2 need more options
  -14: msg 515 not available,
       setting remain unchanged
  '''
  # rval message
  def JsonRval(self, data):
    # allow next msg send out
    if self.msgbusy == data["msg_id"] and data["msg_id"] <> 258:
        self.msgbusy = 0
    # token lost, need to re-new token
    if data["rval"] == -4:
      self.token = 0
      self.link = False
      self.srv.send('{"msg_id":257,"token":0}')
      self.SendMsg('{"msg_id":%d}' %data["msg_id"])
    # error rval < 0, clear msg_id
    elif data["rval"] < 0:
      if data["msg_id"] == 1283:
        self.status["pwd"] = ""
        self.listing = []
        self.lsdir.set()
      data["msg_id"] = 0
    # get token
    if data["msg_id"] == 257:
      self.token = data["param"]
      self.link = True
    # drop token
    elif data["msg_id"] == 258:
      self.token = 0
      self.link = False
      self.UnlinkCamera()
    # all config information
    elif data["msg_id"] == 3:
      self.settings = json.dumps(data["param"], indent=0).replace("{\n","{").replace("\n}","}")
      #self.status["config"] = data["param"]
    # battery status
    elif data["msg_id"] == 13:
      self.status["battery"] = data["param"]
      if data["type"] == "batterty":
        self.status["adapter_status"] = "0"
      else:
        self.status["adapter_status"] = "1"
      print "camera status:\n", json.dumps(self.status, indent=2)
    # take photo
    elif data["msg_id"] == 769:
      self.cambusy = True
    # start record
    elif data["msg_id"] == 513:
      self.recordtime = self.RecordTime(0)
      self.cambusy = True
    # stop record
    elif data["msg_id"] == 514:
      self.recording = False
      self.cambusy = True
    # recording time
    elif data["msg_id"] == 515:
      self.recordtime = self.RecordTime(data["param"])
      if self.showtime and self.recording:
        self.SendMsg('{"msg_id":515}')
    # change dir
    elif data["msg_id"] == 1283:
      self.status["pwd"] = data["pwd"]
    # get file listing
    elif data["msg_id"] == 1282:
      self.listing = self.CreateFileList(data["listing"])
      self.lsdir.set()
    # download file size
    elif data["msg_id"] == 1285:
      self.status["size"] = data["size"]
      self.status["rem_size"] = data["rem_size"]
      self.status["offset"] = data["size"] - data["rem_size"]
      self.dlstart.set()
      
  def RecvMsg(self):
    try:
      if self.socketopen == 0:
        ready = select.select([self.srv], [], [])
        if ready[0]:
          byte = self.srv.recv(1)
          if byte == "{":
            self.jsonon = True
            self.jsonoff += 1
          elif byte == "}":
            self.jsonoff -= 1
          self.recv += byte
          if self.jsonon and self.jsonoff == 0:
            #print "RecvMsg self.recv",self.recv
            self.JsonHandle(json.loads(self.recv))
            self.recv = ""
    except Exception as err:
      self.link = False
      print "RecvMsg error", err, self.recv
      self.recv = ""

  def ThreadRecv(self):
    #print "ThreadRecv Starts\n"
    while self.socketopen: 
      if self.quit.isSet():
        break
    while self.socketopen == 0:
      if self.quit.isSet():
        break
      self.RecvMsg()

  def Connect(self):
    socket.setdefaulttimeout(5)
    #create socket
    self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.srv.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    self.socketopen = self.srv.connect_ex((self.ip, self.port))
    print "socket status: %d" %self.socketopen
    if self.socketopen == 0:
      #print 'sent out: {"msg_id":257,"token":0}'
      self.msgbusy = 257
      self.srv.send('{"msg_id":257,"token":0}')
      self.srv.setblocking(0)

  def Disconnect(self):
    if self.socketopen == 0:
      self.socketopen = -1
      try:
        self.srv.close()
      except:
        pass
      finally:
        self.quit.set()
        self.taken.set()

  def RecordTime(self, seconds):
    rectime = "00:00:00"
    ihour = 0
    iminute = 0
    isecond = 0
    if seconds <> 0:
      ihour = seconds / 3600
      seconds = seconds % 3600
      iminute = seconds / 60
      isecond = seconds % 60
      rectime = "%02d:%02d:%02d" %(ihour, iminute, isecond)
    return rectime
      
  def TakePhoto(self, type="precise quality"):
    if type == "precise quality":
      self.SendMsg('{"msg_id":769}')

  def StartRecord(self, showtime=True):
    self.showtime = showtime
    self.SendMsg('{"msg_id":513}')

  def StopRecord(self):
    self.SendMsg('{"msg_id":514}')
  
  #size can be 0
  def StartDownload(self, file, size=0, offset=0):
    self.dlstart.clear()
    self.dlcomplete.clear()
    self.dlstop.clear()
    self.dlerror.clear()
    self.status["file"] = file
    self.status["offset"] = 0
    self.status["size"] = 0
    self.status["rem_size"] = 0
    if offset > 0:
      print "reconnect", offset
      time.sleep(5)
      #self.srv.send('{"msg_id":257,"token":0}')
    self.SendMsg('{"msg_id":1285,"param":"%s","offset":%d,"fetch_size":%d}' %(file,offset,size))
    while True:
      if self.quit.isSet():
        return
      if self.wifioff.isSet():
        return
      if self.dlstart.isSet():
        print "StartDownload", file, offset
        threading.Thread(target=self.ThreadDownload, args=(file,self.status["size"],self.status["offset"],),name="ThreadDownload").start()
        break

  def ThreadDownload(self, file, total_size, offset):
    try:
      print "ThreadDownload", file, total_size
      ichunk = 2
      chunk_size = [1024,2048,4096,8192,16384,32768]
      self.dlstatus = {}
      percent = "%0.2f" %(float(offset)/float(total_size)*100)
      info = '"file":"{0}","fetch":{1},"remain":{2},"total":{3},"speed":"0.00 B/s","percent":{4}'.format(file,offset,total_size-offset,total_size,percent)
      info = '{%s}'%info
      print 'blank json', info
      self.dlstatus = json.loads(info)
      self.dlstart.clear()
      socket.setdefaulttimeout(10)
      Datasrv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      Datasrv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      Datasrv.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
      Datasrv.connect((self.ip, 8787))
      
      tstart = time.time()
      bytes_per_sec = 0
      fname = __file__.replace(basename(__file__), "files/%s" %file)
      print "saving to", fname
      if offset == 0:
        localfile = open(fname, "wb")
      else:
        localfile = open(fname, "ab")
      bytes_so_far = 0
      while True:
        if self.quit.isSet():
          return
        if self.wifioff.isSet():
          return
        this_size = chunk_size[ichunk]
        #print bytes_so_far, this_size, total_size
        #print float(bytes_so_far)/float(total_size)*100, int(float(bytes_so_far)/float(total_size)*100)
        #self.current_screen.ids.lstSelection.text = "Download %s" %int(float(bytes_so_far)/float(total_size)*100)
        if this_size + bytes_so_far > total_size:
          this_size = total_size - bytes_so_far
        chunk = bytearray(this_size)
        view = memoryview(chunk)
        bytes_per_sec += this_size
        while this_size:
          nbytes = Datasrv.recv_into(view, this_size)
          view = view[nbytes:]
          this_size -= nbytes
          bytes_so_far += nbytes

        localfile.write(chunk)
        
        if bytes_so_far >= total_size:
          break
          
        if self.dlcomplete.isSet():
          info = '"file":"{0}","fetch":{1},"remain":0,"total":{1},"speed":"- - -","percent":100.00'.format(file, total_size)
          info = '{%s}'%info
          print 'running json', info
          self.dlstatus = json.loads(info)
        else:
          tstop = time.time()
          if (tstop - tstart) > 1:
            speed = self.GetFileSize(bytes_per_sec) + "/s"
            percent = "%0.2f" %(float(bytes_so_far)/float(total_size)*100)
            info = '"file":"{0}","fetch":{1},"remain":{2},"total":{3},"speed":"{4}","percent":{5}'.format(file, bytes_so_far, total_size - bytes_so_far, total_size, speed, percent)
            info = '{%s}'%info
            print 'running json', info
            self.dlstatus = json.loads(info)
            tstart = tstop
            bytes_per_sec = 0
      
      self.dlcomplete.wait()
      localfile.write(chunk)
      localfile.close()
      #final chunk
      print bytes_so_far, this_size, total_size, "chunk", len(chunk)
      print "closing Datasrv"
      Datasrv.close()
      self.dlstop.set()
     
    except Exception as err:
      print "ThreadDownload error", err
      # try to reconnect
      self.dlerror.wait(10)
      if self.dlerror.isSet():
        #localfile.write(chunk)
        localfile.close()
        gsize = getsize(fname)
        print "fname", gsize
        print "error wait 30 seconds"
        print "byte_so_far",bytes_so_far
        print "offset",self.status["offset"]
        print "total",self.status["size"]
        print "chunk",len("chunk")
        time.sleep(60)
        self.StartDownload(self.status["file"], self.status["size"], gsize)
      Datasrv.close()
      
  def RefreshFile(self, dir="/tmp/fuse_d/DCIM"):
    self.lsdir.clear()
    self.status["pwd"] = ""
    self.listing = []
    if dir == "":
      self.lsdir.set()
      return
    self.SendMsg('{"msg_id":1283,"param":"%s"}' %dir)
    while True:
      if self.quit.isSet():
        return
      if self.wifioff.isSet():
        return
      if self.lsdir.isSet():
        return
      if self.status["pwd"] <> "":
        break
    if self.status["pwd"] <> "":
      self.SendMsg('{"msg_id":1282,"param":" -D -S"}')
      while not self.lsdir.isSet():
        if self.quit.isSet():
          break
        if self.wifioff.isSet():
          break
          
  def GetFileSize(self, sizebyte):
    value = float(sizebyte)
    option = 0
    while value > 1024:
      value = value/float(1024)
      option += 1
    pres = ["B", "KB", "MB", "GB", "TB"]
    return("%.2f %s" %(value, pres[option]))
    
  def CreateFileList(self, rvalfilelist):
    #print "rvalfilelist", rvalfilelist
    r = []
    if len(rvalfilelist) > 0:
      i = 0
      for item in rvalfilelist:
        i += 1
        fdesc = item[item.keys()[0]].split('|')
        fsize = fdesc[0].replace(' bytes','')
        fdict = '{"name":"%s","byte":%s,"size":"%s","date":"%s"}' %(item.keys()[0],fsize,self.GetFileSize(fsize),fdesc[1])
        #print i, fdict
        #print i, item.keys()[0], item[item.keys()[0]]
        r.append(json.loads(fdict))
    #print "create file list", r
    return r
    
  def FormatCard(self):
    self.SendMsg('{"msg_id":4}')

  def Reboot(self):
    self.SendMsg('{"msg_id":2,"type":"dev_reboot","param":"on"}')

  def RestoreFactory(self):
    self.SendMsg('{"msg_id":2,"type":"restore_factory_settings","param":"on"}')

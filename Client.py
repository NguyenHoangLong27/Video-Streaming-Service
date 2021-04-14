from tkinter import Button, Label, W, E, N, S, messagebox
from PIL import Image, ImageTk
from RtpPacket import RtpPacket
import socket, os, sys, traceback, threading

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:

	SETUP_CODE = 0
	PLAY_CODE = 1
	PAUSE_CODE = 2
	TEARDOWN_CODE = 3

	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	RTSP_VER = "RTSP/1.0"
	TRANSPORT = "RTP/UDP"

	def __init__(self, master, serverAddr, serverPort, rtpPort, filename):
		"""Initializing..."""
		self.master = master
		self.serverAddr = serverAddr
		self.serverPort = int(serverPort)
		self.rtpPort = int(rtpPort)
		self.fileName = filename

		self.serverConnect()
		self.buildGUI()	

		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.frameNbr = 0

	def serverConnect(self):
		"""Open RTSP session with server."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.rtspSocket.connect((self.serverAddr, self.serverPort))
		
	def buildGUI(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.play = Button(self.master, width=20, padx=3, pady=3)
		self.play["text"] = "Play"
		self.play["command"] = self.playMovie
		self.play.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.teardownMovie
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
	
	def setupMovie(self):
		"""Setup button."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP_CODE)
	
	def playMovie(self):
		"""Play button."""
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY_CODE)

	def pauseMovie(self):
		"""Pause button."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE_CODE)
	
	def teardownMovie(self):
		"""Teardown button."""
		self.sendRtspRequest(self.TEARDOWN_CODE)		
		self.master.destroy() # Close the gui window
		os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video
	
	def sendRtspRequest(self, requestNumber):
		"""Send RTSP request to the server."""	
		# Setup request
		if requestNumber == self.SETUP_CODE and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
        
			self.rtspSeq+=1
			
			# C: SETUP movie.Mjpeg RTSP/1.0
			# C: CSeq: 1
			# C: Transport: RTP/UDP; client_port: 102X
			request ="%s %s %s" % (self.SETUP,self.fileName,self.RTSP_VER) 
			request+="\nCSeq: %d" % self.rtspSeq
			request+="\nTransport: %s; client_port= %d" % (self.TRANSPORT,self.rtpPort)
			
			self.requestSent = self.SETUP_CODE
			
		# Play request
		elif requestNumber == self.PLAY_CODE and self.state == self.READY:
        
			self.rtspSeq+=1
			
			# C: PLAY movie.Mjpeg RTSP/1.0
			# C: CSeq: ...
			# C: Session: ...
			request ="%s %s %s" % (self.PLAY,self.fileName,self.RTSP_VER)
			request+="\nCSeq: %d" % self.rtspSeq
			request+="\nSession: %d"%self.sessionId
                
			self.requestSent = self.PLAY_CODE
            
        # Pause request
		elif requestNumber == self.PAUSE_CODE and self.state == self.PLAYING:
        
			self.rtspSeq+=1
			
			# C: PAUSE movie.Mjpeg RTSP/1.0
			# C: CSeq: ...
			# C: Session: ...
			request ="%s %s %s" % (self.PAUSE,self.fileName,self.RTSP_VER)
			request+="\nCSeq: %d" % self.rtspSeq
			request+="\nSession: %d"%self.sessionId
			
			self.requestSent = self.PAUSE_CODE
			
		# Teardown request
		elif requestNumber == self.TEARDOWN_CODE and not self.state == self.INIT:

			self.rtspSeq+=1
			
			# C: TEARDOWN movie.Mjpeg RTSP/1.0
			# C: CSeq: ...
			# C: Session: ...
			request ="%s %s %s" % (self.TEARDOWN, self.fileName, self.RTSP_VER)
			request+="\nCSeq: %d" % self.rtspSeq
			request+="\nSession: %d" % self.sessionId
			
			self.requestSent = self.TEARDOWN_CODE

		else:
			return
		
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode())
		print(request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			
			# If the request is TEARDOWN close the RTSP socket of the client
			if self.requestSent == self.TEARDOWN_CODE:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		reply = data.split('\n')
		repSeq = int(reply[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if repSeq == self.rtspSeq:
			session = int(reply[2].split(' ')[1])
			# Get the sessionId from server's reply
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(reply[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP_CODE:

						# Update RTSP state.
						self.state = self.READY
						
						# Open RTP port.
						self.openRtpPort() 
					elif self.requestSent == self.PLAY_CODE:
						self.state = self.PLAYING
					elif self.requestSent == self.PAUSE_CODE:
						self.state = self.READY
                        
						self.playEvent.set()
					elif self.requestSent == self.TEARDOWN_CODE:
						self.state = self.INIT
				# Print out server's reply
				print("\n" + data + "\n")


	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
		# Set the timeout value of the socket
		self.rtpSocket.settimeout(0.5)
		
		# Bind the socket to the address using the RTP port given by the client user.
		self.rtpSocket.bind(('',self.rtpPort))

	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket=RtpPacket()
					rtpPacket.decode(data)
					
					currFrame = rtpPacket.seqNum()
										
					if currFrame > self.frameNbr:
						self.frameNbr = currFrame
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet(): 
					break
				
				# If the request is TEARDOWN close the RTSP socket of the client
				if self.requestSent==self.TEARDOWN_CODE:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
					
	def writeFrame(self, data):
		"""Write the received frame to a image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file=open(cachename, "wb")
		file.write(data)
		file.close()
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo



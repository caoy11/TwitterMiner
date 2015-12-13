from django.shortcuts import render
import datetime
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from TwitterStream.models import Tweet
from django.shortcuts import render_to_response  
from threading import Thread
import boto.sqs
from boto.sqs.message import Message
import boto.sns
import requests
from multiprocessing import Pool
import os
import tweepy
from tweepy.api import API
import json
import sys
import urllib2
import urllib
import traceback
# from nltk.tokenize import RegexpTokenizer
# from stop_words import get_stop_words
# from nltk.stem.porter import PorterStemmer
# from gensim import corpora, models
# import gensim


consumer_token = 'fIexLb754zx6X29gltYOkvFBR'
consumer_secret = 'nyeaLUtuRRpBydnl27lEFbqD7oUMK83cLi2j71kCFdsD2KXacA'

requesttoken = None
myStream = None
conn = None
messagequeue = None
resultqueue = None
poolthread = None
snsurl = None
snsclient = None

class MyStreamListener(tweepy.StreamListener):
	def __init__(self, queue=None, api=None):
		self.messagequeue = queue
		self.api = api or API()

	def on_status(self, status):
		try:
			if not status.coordinates == None:
				newtweet = Tweet(content = status.text, longitude = status.coordinates['coordinates'][0], 
					latitude = status.coordinates['coordinates'][1], 
					topic = '', 
					date = status.created_at)
				newtweet.save()
				print 'save'
				if self.messagequeue:
					s = Message()
					s.set_body(status.text)
					self.messagequeue.write(s)
					print 'write'
			#print '\n %s  %s  %s\n' % (status.text, status.created_at, status.coordinates)
		except Exception, e:
			# Catch any unicode errors while printing to console
			# and just ignore them to avoid breaking application.
			print e

# Create your views here.

def process():
	#to do
	global conn
	global messagequeue
	global poolthread
	global resultqueue
	global snsclient
	while True:
		try:
			if messagequeue:
				messages = messagequeue.get_messages(num_messages=1)
				if len(messages) > 0:
					message = messages[0]
					url = 'http://gateway-a.watsonplatform.net/calls/text/TextGetTextSentiment'
					parameters = {'apikey' : '10c190efcc217f6a442aa9878736adaf95c284bd', 'text':message.get_body(), 'outputMode':'json'}
					response = requests.get(url, params=parameters)
					result = json.loads(response.text)
					if not result['status'] == 'OK':
						continue
					mes = {
						'type':result['docSentiment']['type'],
						'text':message.get_body()
					}
					snsclient.publish(topic = 'arn:aws:sns:us-west-2:357170364786:Twitter', message = json.dumps(mes))
					messagequeue.delete_message(message)
					print "publish"
					# if resultqueue:
					# 	s = Message()
					# 	s.set_body(json.dumps(mes))
					# 	resultqueue.write(s)
		except Exception, e:
				# Catch any unicode errors while printing to console
				# and just ignore them to avoid breaking application.
				exc_type, exc_value, exc_traceback = sys.exc_info()
				traceback.print_exception(exc_type, exc_value, exc_traceback)

def workerPool():
	global conn
	global messagequeue
	global poolthread
	global resultqueue
	pool = Pool(processes = 5)
	while True:
		if messagequeue:
			mes = messagequeue.get_messages(num_messages=10)
			result = pool.map(process, mes)

def createSQS():
	global conn
	global messagequeue
	global poolthread
	global resultqueue
	global snsclient
	if not conn:
		conn = boto.sqs.connect_to_region("us-west-2",
			aws_access_key_id='AKIAJ225EQ57HSH35LPA',
			aws_secret_access_key='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')
		snsclient = boto.sns.connect_to_region("us-west-2",
			aws_access_key_id='AKIAJ225EQ57HSH35LPA',
			aws_secret_access_key='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')
		messagequeue = conn.create_queue('tweets')
		resultqueue = conn.create_queue('sentiments')

def createWorkerPool():
	global conn
	global messagequeue
	global poolthread
	global resultqueue
	if not poolthread:
		poolthread = Thread(target = process)
		poolthread.start()

def justtest(request):
	global messagequeue
	global resultqueue
	global snsurl
	#result = request.POST.get('SubscribeURL')
	try:
		snsurl = """dir(request.GET)"""
		return HttpResponse("")
	except Exception, e:
		snsurl = "123"
		return HttpResponse("")
	# if resultqueue:
	# 	s = Message()
	# 	s.set_body(result)
	# 	resultqueue.write(s)

def processSNSUrl(request):
	global snsurl
	return HttpResponse(json.dumps(snsurl))

def getSentiments(request):
	global conn
	global messagequeue
	global poolthread
	global resultqueue
	res = []
	if resultqueue:
		result = resultqueue.get_messages(num_messages=10)
		for mes in result:
			body = json.loads(mes.get_body())
			res.append(body['Message'])
			resultqueue.delete_message(mes)
	final = json.dumps(res)
	return HttpResponse(final)

def index(request):
	global myStream
	createSQS()
	createWorkerPool()
	if myStream:
		print myStream.running
	if myStream and myStream.running:
		return HttpResponseRedirect('/TwitterStream/test/')
	auth = tweepy.OAuthHandler(consumer_token, consumer_secret)#, 'http://127.0.0.1:8000/TwitterStream/redirect/')
	try:
		redirect_url = auth.get_authorization_url()
	except tweepy.TweepError as e:
		print e
		print 'Error! Failed to get request token.'
	global requesttoken
	requesttoken = auth.request_token
	return HttpResponseRedirect(redirect_url)

def redirect(request):
	verifier = request.GET.get('oauth_verifier')
	auth = tweepy.OAuthHandler(consumer_token, consumer_secret)
	global requesttoken
	global messagequeue
	auth.request_token = requesttoken
	try:
		auth.get_access_token(verifier)
	except tweepy.TweepError as e:
		print e
		print e.reason
		print 'Error! Failed to get access token.'
	try:
		auth.set_access_token(auth.access_token, auth.access_token_secret)
		api = tweepy.API(auth)
		myStreamListener = MyStreamListener(queue=messagequeue)
		global myStream
		myStream = tweepy.Stream(auth = api.auth, listener=myStreamListener)
		myStream.filter(track=['food', 'music', 'book', 'movie', 'game', 'sports', 'the', 'a', 
			'and', 'to', 'i', 'in', 'it', 'you', 'of', 'for', 'on'], async=['true'])
	except Exception as e:
		print e
		print 'Error! Failed to get tweets.'
	return HttpResponseRedirect('/TwitterStream/test/')

def testwebpage(request):
	return render_to_response('resource/html/test.html') 

def getnewtweets(request):
	final = ''
	try:
		timefrom =  request.GET.get('timefrom','')
		timeto =  request.GET.get('timeto','')
		#Fri, 16 Oct 2015 21:28:41 GMT
		ctimefrom = datetime.datetime.strptime(timefrom, '%a, %d %b %Y %H:%M:%S %Z')+ datetime.timedelta(seconds = -10)
		ctimeto = datetime.datetime.strptime(timeto, '%a, %d %b %Y %H:%M:%S %Z')+ datetime.timedelta(seconds = -10)
		tweetlist = Tweet.objects.filter(date__range = (ctimefrom, ctimeto))
		res = []
		for tweet in tweetlist:
			res.append({'date':str(tweet.date), 
				'content': tweet.content, 
				'latitude': tweet.latitude,
				'longitude': tweet.longitude,
				'topic': tweet.topic})
		final = json.dumps(res)
	except Exception as e:
		print e
	return HttpResponse(final)

def getTweetswithFilter(request):
	final = ''
	try:
		filter = request.GET.get('filter','all')
		tweetlist = None
		if filter == 'all':
			tweetlist = Tweet.objects.all()
		else:
			tweetlist = Tweet.objects.filter(content__contains = filter)
		res = []
		for tweet in tweetlist:
			res.append({'date':str(tweet.date), 
				'content': tweet.content, 
				'latitude': tweet.latitude,
				'longitude': tweet.longitude,
				'topic': tweet.topic})
		final = json.dumps(res)
	except Exception as e:
		print e
	return HttpResponse(final)

def getTweetswithTopic(request):
	topic = request.GET.get('topic','')
	tweetlist = Tweet.objects.filter(topic = topic)
	return HttpResponse(json.dumps(tweetlist))

def getTopTopics(request):
	topiclist = [['home', 0.28], ['today', 0.12], ['can', 0.19], ['fak', 0.12], ['go', 0.17], ['selangor', 0.14], 
	['istanbul', 0.14], ['thank', 0.11], ['interest', 0.15], ['rkiy', 0.26], ['bangkok', 0.06],['anyon', 0.2],
	['recommend', 0.19],['retail', 0.14],['cafe', 0.14],['johor', 0.1],['market', 0.08],['engin', 0.08],['love', 0.11],
	['univers', 0.09],['school', 0.08],['music', 0.08],['jaya', 0.08],['niversitesi', 0.12],['stanbul', 0.24],['ltesi', 0.05],
	['ankara', 0.1],['like', 0.13],['que', 0.08],['come', 0.06],['call', 0.06]]
	return HttpResponse(json.dumps(topiclist))

def getLDA(request):
	return HttpResponse('')
	# tokenizer = RegexpTokenizer(r'\w+')
	# stop = get_stop_words('en')
	# p_stemmer = PorterStemmer()
	# tweetlist = Tweet.objects.all()
	# doc_set = []
	# for tweet in tweetlist:
	# 	doc_set.append(tweet.content)
	# texts = []
	# for i in doc_set:
	#     doc = i.lower()
	#     tokens = tokenizer.tokenize(doc)
	#     stopped_tokens = [i for i in tokens if not i in stop]
	#     stemmed_tokens = [p_stemmer.stem(i) for i in stopped_tokens]
	#     texts.append(stemmed_tokens)
	# dictionary = corpora.Dictionary(texts)
	# corpus = [dictionary.doc2bow(text) for text in texts]
	# ldamodel = gensim.models.ldamodel.LdaModel(corpus, num_topics=20, id2word = dictionary, passes=30)
	# return HttpResponse(json.dumps(ldamodel.print_topics(num_topics=10, num_words=5)))

	#result
	# "0.028*home + 0.006*bangkok + 0.005*selangor + 0.005*alam + 0.005*recommend", 
	# "0.012*today + 0.012*7 + 0.011*f + 0.011*st + 0.011*9",
	# "0.019*can + 0.020*anyon + 0.019*recommend + 0.014*retail + 0.014*cafe", 
	# "0.012*fak + 0.010*johor + 0.008*market + 0.008*engin + 0.007*im", 
	# "0.017*go + 0.010*other + 0.009*ve + 0.009*2 + 0.008*life + 0.007*k", 
	# "0.014*selangor + 0.011*w + 0.010*ankara + 0.008*una + 0.008*jaya", 
	# "0.014*istanbul + 0.010*na + 0.009*com + 0.008*school + 0.008*music ", 
	# "0.011*thank + 0.011*love + 0.009*univers + 0.008*don + 0.007*day", 
	# "0.015*interest + 0.013*like + 0.008*que + 0.006*come + 0.006*call", 
	# "0.026*rkiy + 0.024*stanbul + 0.012*niversitesi + 0.005*ltesi + 0.004*s"













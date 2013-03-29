#!/usr/bin/python

import os
import re
import sys
import commands
import tweepy
import gdata
import gdata.youtube
import gdata.youtube.service
import mechanize
import ConfigParser
import logging

def get_bool(string):
	if string.lower() == 'yes' or string.lower() == 'true':
		return True
	elif string.lower() == 'no' or string.lower() == 'false':
		return False
	else:
		raise Exception("wrong value \'%s\'".format(string))	

class ShazamInfo:
	def __init__(self):
		self.url = ""
		self.title = ""

class MediaInfo:
	def __init__(self):
		self.url = ""
		self.title = ""

class ShazamTag:
	def __init__(self):
		self.object = None
		self.author = "Unknown Author"
		self.title = "Unknown Title"
		self.album = "Unknwon Album"
		self.genre = "N/A"
		self.shazam = ShazamInfo()
		self.soundhound = ShazamInfo()
		self.media = MediaInfo()
		self.filename = ""

class YouTubeClient:
	def __init__(self):
		self._yt_service = gdata.youtube.service.YouTubeService()
	
	def find_media(self, tags):
		newtags = list()
		for tag in tags:
			try:
				feed = self._get_feed(tag.shazam.title)
				item = self._get_best_entry(feed)
				self._print_item(item)
				tag.media.url = item.media.player.url
				tag.media.title = item.media.title.text
				newtags.append(tag)
			except:
				continue
		return newtags


	def _print_item(self, entry):
		print '[YouTube] Title: %s' % entry.media.title.text
		print '[YouTube] URL  : %s' % entry.media.player.url

	def _get_best_entry(self, feed):
		return feed.entry[0]

	def _get_feed(self, title):
		query = gdata.youtube.service.YouTubeVideoQuery()
		query.vq = title
		query.orderby = 'relevance'
		query.racy = 'include'
		query.hd = True
		feed = self._yt_service.YouTubeQuery(query)
		return feed

class TwitterClient:
	def __init__(self, config):
		self._remove_tweet = get_bool(config.get('Twitter', 'remove_tweet'))
		self._consumer_key = config.get('Twitter', 'consumer_key')
		self._consumer_secret = config.get('Twitter', 'consumer_secret')
		self._access_token = config.get('Twitter', 'access_token')
		self._access_token_secret = config.get('Twitter', 'access_token_secret')
		logging.debug('[Twitter][init] remove_tweet: %s', self._remove_tweet)
		logging.debug('[Twitter][init] consumer_key: %s', self._consumer_key)
		logging.debug('[Twitter][init] consumer_secret: %s', self._consumer_secret)
		logging.debug('[Twitter][init] access_token: %s', self._access_token)
		logging.debug('[Twitter][init] access_token_secret: %s', self._access_token_secret)
		self._connect()

	def get_latest_tags(self):
		tweets = self._get_latest_tweets()
		tags = list()
		for tweet in tweets:
			tag = ShazamTag()
			tag.object = tweet
			tag.shazam.url = self._get_shazam_url(tweet)
			tag.soundhound.url = self._get_soundhound_url(tweet)
			tags.append(tag)
		return tags

	def remove_tag(self, tag):
		if not self._remove_tweet:
			return False
		try:
			self._api.destroy_status(tag.object.id)
			return True
		except:
			return False

	def _connect(self):
		try:
			self._auth = tweepy.OAuthHandler(self._consumer_key, self._consumer_secret)
			self._auth.set_access_token(self._access_token, self._access_token_secret)
			self._api = tweepy.API(self._auth)
			return True
		except:
			return False


	def _get_latest_tweets(self):
		tweets = self._api.user_timeline()
		return tweets	

	def _get_shazam_url(self, tweet):
		if 'urls' in tweet.entities:
			for url in tweet.entities['urls']:
				if 'expanded_url' in url:
					urlstr = str(url['expanded_url'])
					if 'shz' in urlstr or 'shazam' in urlstr:
						print '[Twitter] Tweet: %s' % tweet.text
						print '[Twitter] URL  : %s' % urlstr
						return urlstr
		return None
	
	def _get_soundhound_url(self, tweet):
		if 'urls' in tweet.entities:
			for url in tweet.entities['urls']:
				if 'expanded_url' in url:
					urlstr = str(url['expanded_url'])
					if 'soundhound' in urlstr:
						print '[Twitter] Tweet: %s' % tweet.text
						print '[Twitter] URL  : %s' % urlstr
						return urlstr
		return None    

class ShazamParser:
	def __init__(self, config):
		self._br = mechanize.Browser()
		self._re = re.compile('^(?P<author>[^:]+) : (?P<title>.*)')

	def parse_title(self, tag):
		url = tag.shazam.url
		self._br.open(tag.shazam.url)
		title = self._br.title()
		try:
			m = self._re.match(title)
			a = m.group('author')
			t = m.group('title')
			tag.author = a 
			tag.title = t
		except:
			logging.debug('[Shazam ] %s', sys.exc_info()[1])
		tag.shazam.title = title
		return tag

	def parse_titles(self, tags):
		newtags = list()
		for tag in tags:
			newtags.append(tag)
			try:
				self.parse_title(tag)
				print '[Shazam ] URL  : %s' % tag.shazam.url
				print '[Shazam ] Title: %s' % tag.shazam.title
			except:
				continue
		return newtags

class SoundHoundParser:
	def __init__(self, config):
		self._br = mechanize.Browser()

	def parse_title(self, tag):
		html = self._br.open(tag.soundhound.url).read()
		match = re.search('<div class="trackName">(?P<title>.*?)</div>.*?<div class="artistName">.*?<a href=.*?>(?P<author>.*?)</a></div>', html, re.DOTALL)
		if match!=None:
			tag.author = match.group('author')
			tag.title = match.group('title')
		tag.shazam.title = "%s : %s" % (tag.author, tag.title)
		return tag

	def parse_titles(self, tags):
		newtags = list()
		for tag in tags:
			newtags.append(tag)
			try:
				self.parse_title(tag)
				print '[SoundHound ] URL  : %s' % tag.soundhound.url
				print '[SoundHound ] Title: %s' % tag.shazam.title
			except:
				continue
		return newtags

class YouTubeDl:
	def __init__(self):
		self._app = "youtube-dl"	
	
	def download(self, url, file_name):
		print '[Download] URL : %s' % url
		print '[Download] File: %s' % file_name
		os.system("{0} -o \'{1}\' \"{2}\"".format(self._app, file_name, url))

	def get_filename(self, url, filename):
		cmd = "{0} --get-filename -o \'{1}.%(ext)s\' \"{2}\"".format(self._app, filename, url)
		status, output = commands.getstatusoutput(cmd)
		return output
		
	def get_format(self, url):
		cmd = "{0} --get-format \"{1}\"".format(self._app, url)
		status, output = commands.getstatusoutput(cmd)
		return output

class Pysh:
	def __init__(self, config):
		self._dir = config.get('Output', 'dir')
		if self._dir == "":
			self._dir = os.getcwd()
		else:
			self._dir = self._dir.replace('\\', '/')
			if self._dir[-1] == '/':
				self._dir = self._dir[:-1]
			if not os.path.exists(self._dir) or not os.path.isdir(self._dir):
				raise Exception("directory \'{0}\' does not exists".format(self._dir)) 
		logging.debug('[Pysh   ][init] Dir: \'%s\'', self._dir)
		self._name = config.get('Output', 'name')
		self._audio = get_bool(config.get('Output', 'audio'))
		self._audio_format = config.get('Output', 'audio_format')
		self._video = get_bool(config.get('Output', 'video'))

	def get_path(self, tag):
		path = self._name
		path = path.replace("\"", "")
		path = path.replace("%a", tag.author)
		path = path.replace("%t", tag.title)
		path = path.replace("%A", tag.album)
		#TODO: rest of wildcards
		if path[0] == '/':
			path = path[1:]
		path = self._dir + '/' + path
		return path

	
def main():
	logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

	config = ConfigParser.RawConfigParser()
	config.read('pysh.config')
	
	pysh = Pysh(config)

	twitter = TwitterClient(config)
	shparser = ShazamParser(config)
	sohoparser = SoundHoundParser(config)
	youtube = YouTubeClient()
	dl = YouTubeDl()
	tags = twitter.get_latest_tags()
	tags = shparser.parse_titles(tags)
	tags = sohoparser.parse_titles(tags)
	tags = youtube.find_media(tags)
	for tag in tags:
		tag.filename = dl.get_filename(tag.media.url, pysh.get_path(tag))
		if not os.path.exists(tag.filename):
			print '[main   ] Downloading: %s' % tag.filename
			dl.download(tag.media.url, tag.filename)
		else:
			print '[main   ] Skipping file: %s' % tag.filename
		twitter.remove_tag(tag)


if __name__ == '__main__':
	try:
		main()
	except:
		print "error: ", sys.exc_info()[1]


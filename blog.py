import os
import re
import string
import random

import hashlib
import hmac

import jinja2
import webapp2

import datetime

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape=True)

secret = 'lovewifey'

PW_RE = re.compile(r"^.{3,20}$")
USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
EMAIL_RE = re.compile(r"^[\S]+@[\S]+.[\S]+$")

def render_str(template, **params):
	t = jinja_env.get_template(template)
	return t.render(params)

def render_post(response, post):
	response.out.write('<b>' + post.subject + '</b><br>')
	response.out.write(post.content)

def blog_key(name = 'default'):
	return db.Key.from_path('blogs', name)

def users_key(group = 'default'):
	return db.Key.from_path('users', group)

def valid_pw(name, password, h):
	salt = h.split('|')[0]
	return h == make_pw_hash(name, password, salt)

def make_pw_hash(name, pw, salt = None):
	if not salt:
		salt = make_salt()
	h = hashlib.sha256(name + pw + salt).hexdigest()
	return '%s|%s' % (salt, h)

def make_salt():
	return ''.join(random.choice(string.letters) for x in xrange(5))

def make_secure_val(val):
	return "%s|%s" % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
	val = secure_val.split('|')[0]
	if secure_val == make_secure_val(val):
		return val

def valid_username(username):
	return username and USER_RE.match(username)

def valid_password(password):
	return password and PW_RE.match(password)

def valid_email(email):
	return not email or EMAIL_RE.match(email)

def read_secure_cookie(self, name):
	cookie_val = self.request.cookies.get(name)
	return cookie_val and check_secure_val(cookie_val)


class Post(db.Model):
	subject = db.StringProperty(required = True)
	content = db.TextProperty(required = True, indexed = False)
	created = db.DateTimeProperty(auto_now_add = True)
	last_modified = db.DateTimeProperty(auto_now = True)
	created_by = db.StringProperty()

	def render_str(self, template, **params):
		t = jinja_env.get_template(template)
		return t.render(params)

	def render(self):
		self._render_text = self.content.replace('/n', '<br>')
		return self.render_str("post.html", p = self)

class User(db.Model):
	name = db.StringProperty(required = True)
	pw_hash = db.StringProperty(required = True)
	email = db.StringProperty()

	@classmethod
	def by_id(cls, uid):
		return cls.get_by_id(uid, parent = users_key())
	
	@classmethod
	def by_name(cls, name):
		u = cls.all().filter('name =', name).get()
		return u

	@classmethod
	def register(cls, name, pw, email = None):
		pw_hash = make_pw_hash(name, pw)
		return User(parent = users_key(),
					name = name,
					pw_hash = pw_hash,
					email = email)

	@classmethod
	def login(cls, name, pw):
		u = cls.by_name(name)
		if u and valid_pw(name, pw, u.pw_hash):
			return u

class BlogHandler(webapp2.RequestHandler):
	def write(self, *a, **kw):
		self.response.out.write(*a, **kw)

	def render_str(self, template, **params):
		return render_str(template, **params)

	def render(self, template, **kw):
		self.write(self.render_str(template, **kw))

	def set_secure_cookie(self, name, val):
		cookie_val = make_secure_val(val)
		self.response.headers.add_header(
			'Set-Cookie',
			'%s=%s; Path=/' % (name, cookie_val))

	def read_secure_cookie(self, name):
		cookie_val = self.request.cookies.get(name)
		return cookie_val and check_secure_val(cookie_val)

	def login(self, user):
		self.set_secure_cookie('user_id', str(user.key().id()))

	def logout(self):
		self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

	def initialize(self, *a, **kw):
		webapp2.RequestHandler.initialize(self, *a, **kw)
		name = self.read_secure_cookie('user_id')
		self.user = name and User.by_name(str(name))

	def valid_username(username):
		return username and USER_RE.match(username)

	def valid_password(password):
		return password and PW_RE.match(password)

	def valid_email(email):
		return not email or EMAIL_RE.match(email)

	def pw_check(password, verify):
		if password == verify:
			return True
		else:
			return False

	def make_salt():
		return ''.join(random.choice(string.letters) for x in xrange(5))

	def make_pw_hash(name, pw, salt = None):
		if not salt:
			salt = make_salt()
		h = hashlib.sha256(name + pw + salt).hexdigest()
		return '%s|%s' % (salt, h)

	def valid_pw(name, password, h):
		salt = h.split('|')[0]
		return h == make_pw_hash(name, password, salt)

	def users_key(group = 'default'):
		return db.Key.from_path('users', group)

	def make_secure_val(val):
		return "%s|%s" % (val, hmac.new(secret, val).hexdigest())

	def check_secure_val(secure_val):
		val = secure_val.split('|')[0]
		if secure_val == make_secure_val(val):
			return val

class BlogFront(BlogHandler):
	def get(self):
		posts = db.GqlQuery("SELECT * FROM Post order by created desc limit 10")
		self.render('main.html', posts = posts)

class PostPage(BlogHandler):
	def get(self, post_id):
		key = db.Key.from_path('Post', int(post_id), parent=blog_key())
		post = db.get(key)

		if not post:
			self.error(404)
			return

		self.render("permalink.html", post=post)

class Signup(BlogHandler):
	def get(self):
		self.render("signup.html")

	def post(self):
		have_error = False
		username = self.request.get('username')
		password = self.request.get('password')
		verify = self.request.get('verify')
		email = self.request.get('email')

		params = dict(username = username,
					  email = email)

		if not valid_username(username):
			params['error_username'] = "That's not a valid username."
			have_error = True

		if not valid_password(password):
			params['error_password'] = "That wasn't a valid password."
			have_error = True
		elif password != verify:
			params['error_verify'] = "Your passwords didn't match."
			have_error = True

		if not valid_email(email):
			params['error_email'] = "That's not a valid email."
			have_error = True

		if have_error:
			self.render('signup.html', **params)
		else:
			u = User.by_name(username)
			if u:
				msg = "That user already exists."
				self.render("signup.html", error_username = msg)
			else:
				u = User.register(username, password, email)
				u.put()
				self.login(u)
				self.redirect('/welcome')
		


class Newpost(BlogHandler):
	def get(self):
		self.render("newpost.html")

	def post(self):
		subject = self.request.get("subject")
		content = self.request.get("content")

		if subject and content:
			p = Post(parent = blog_key(), subject = subject, content = content)
			p.put()
			self.redirect("/%s" % str(p.key().id()))
		else:
			error = "Please include both a subject and a blog post."
			self.render("newpost.html", subject = subject, content = content, error = error)

class Welcome(BlogHandler):
	def get(self):
		if read_secure_cookie:
			user_id = self.request.cookies.get("user_id").split("|")[0]
			user_key = db.Key.from_path('User', long(user_id), parent=users_key())
			user = db.get(user_key)
			if user.name:
				self.render("welcome.html", username = user.name)
			else:
				self.redirect('/signup')

class Login(BlogHandler):
	def get(self):
		self.render("login.html")

	def post(self):
		username = self.request.get("username")
		password = self.request.get("password")

		u = User.login(username, password)

		if u:
			self.login(u)
			self.redirect('/welcome')
		else:
			error = "Invalid Login"
			self.render("login.html", error_login = error)

class Logout(BlogHandler):
	def get(self):
		self.logout()
		self.redirect('/signup')

app = webapp2.WSGIApplication([('/', BlogFront),
							   ('/signup', Signup),
							   ('/newpost', Newpost),
							   ('/([0-9]+)', PostPage),
							   ('/welcome', Welcome),
							   ('/login', Login),
							   ('/logout', Logout),
								],
								debug=True)
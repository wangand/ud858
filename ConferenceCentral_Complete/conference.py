#!/usr/bin/env python

# name: Andrew Wang
# Full Stack Web Developer Nanodegree
# Project 4 Conference Organization App

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""


from datetime import datetime

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import StringMessage
from models import BooleanMessage
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms
from models import TeeShirtSize
from models import Session
from models import SessionForm
from models import SessionForms
from models import WebSafeKeys
from models import WebSafeKeyQuery
from models import SessionTypeForm
from models import SessionSpeakerForm
from models import WishListQuery
from models import WishListDelete
from models import SessionKeyQuery
from models import SessionQuery
from models import SessionKeys
from models import SessionKeyQuery
from models import Wishlist

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId


__author__ = 'wesc+api@google.com (Wesley Chun)'


EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
MEMCACHE_FEATURED_KEY = "FEATURED SPEAKER"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')
FEATURED_TPL = ('The featured speaker is: %s in the sessions: ')
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

SDEFAULTS = {
    "highlights": "",
    "duration": 0,
    "startTime": 0,
    "typeOfSession": "LECTURE"
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS = {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
         }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESS_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1,
                                              required=True),
)

SESS_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
               allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID,
                                   ANDROID_CLIENT_ID, IOS_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object,
         returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name'"
                                                " field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10],
                                                  "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10],
                                                "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
                      'conferenceInfo': repr(request)},
                      url='/tasks/send_confirmation_email')
        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' %
                request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
                      http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                                              'No conference found with key:'
                                              ' %s' %
                                              request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf,
                                              getattr(prof, 'displayName'))
                   for conf in confs]
        )

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"],
                                                   filtr["operator"],
                                                   filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name)
                     for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains "
                                                    "invalid field or"
                                                    " operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previously
                # disallow the filter if inequality was
                # performed on a different field before
                # track the field on which the inequality operation
                # is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter "
                                                        "is allowed on "
                                                        "only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId))
                      for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf,
                                                  names[conf.organizerUserId])
                       for conf in conferences])


# - - - Session objects - - - - - - - - - - - - - - - - - - -

    def _createSessionObject(self, request):
        """Create a session object, return SessionForm"""
        # check for authentication
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # get parent Conference from request; raise exception if not found
        c_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' %
                request.websafeConferenceKey)

        if not request.sessionName:
            raise endpoints.BadRequestException(
                "Session 'sessionName' field required")

        # check that user is owner of given conference
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can add a session to the conference.')

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        del data['websafeConferenceKey']
        del data['websafeKey']

        # add default values for those missing
        for df in SDEFAULTS:
            if data[df] in (None, []):
                data[df] = SDEFAULTS[df]
                setattr(request, df, SDEFAULTS[df])

        # convert dates from strings; set month based on start_date
        if data['date']:
            data['date'] = datetime.strptime(data['date'][:10],
                                             "%Y-%m-%d").date()

        # convert type of session to uppercase
        data['typeOfSession'] = data['typeOfSession'].upper()

        # generate Session ID based on Conference ID
        s_id = Conference.allocate_ids(size=1, parent=c_key)[0]
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key

        # return a session form with the same data as in the datastore
        newSess = Session(**data)
        newSess.put()

        # TASK 4
        # Check for featured speaker
        taskqueue.add(params={'sessionKey': s_key.urlsafe()},
                      url='/tasks/set_featured')

        return self._copySessionToForm(newSess)

    def _copySessionToForm(self, sess):
        """Copy relevant fields from Session to SessionForm."""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                # convert date to date string; just copy others
                if field.name.endswith('date'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            elif field.name == "websafeKey":
                setattr(sf, field.name, sess.key.urlsafe())
        sf.check_initialized()
        return sf

    @endpoints.method(SESS_POST_REQUEST, SessionForm, path='session',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create a new Session"""
        return self._createSessionObject(request)

    def _getSessionsFromConference(self, request):
        """Returns an iterator with all sessions of conference"""
        # get the Conference object to query from request; bail if not found
        c_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' %
                request.websafeConferenceKey)

        # return ancestor query for all key matches for this conference
        return Session.query(ancestor=c_key)

    @endpoints.method(SESS_GET_REQUEST, SessionForms,
                      path='session/{websafeConferenceKey}',
                      http_method='GET',
                      name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Get all sessions of a conference"""
        # get all key matches for this conference
        sessions = self._getSessionsFromConference(request).fetch()

        # return set of SessionForm objects per Conference
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions])

    @endpoints.method(SessionTypeForm, SessionForms, path='session/type',
                      http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Get sessions of a conference by type"""
        # Check inputs for sessionType
        if not request.sessionType:
            raise endpoints.BadRequestException(
                "'sessionType' field required")

        # get all key matches for this conference
        # case insensitive search
        upper = request.sessionType.upper()
        sess = self._getSessionsFromConference(request)
        sess = sess.filter(Session.typeOfSession == upper).fetch()

        # return set of SessionForm objects per Conference per given type
        return SessionForms(
            items=[self._copySessionToForm(s) for s in sess])

    @endpoints.method(SessionSpeakerForm, SessionForms,
                      name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """Get all sessions by speaker"""
        if not request.speaker:
            raise endpoints.BadRequestException("'speaker' field required")

        query = Session.query()
        query = query.filter(Session.speaker == request.speaker).fetch()

        # return set of SessionForm objects that share the same speaker
        return SessionForms(
            items=[self._copySessionToForm(s) for s in query])


# - - - Wishlist interface  - - - - - - - - - - - - - - - - -

    @endpoints.method(WishListQuery, WishListQuery,
                      name="addSessionToWishlist")
    def addSessionToWishlist(self, request):
        """This function adds given session to wishlist."""
        # check for authentication
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # check for SessionKey
        if not request.SessionKey:
                raise endpoints.BadRequestException(
                    "'SessionKey' field required")

        # Try and get the session object
        s_key = ndb.Key(urlsafe=request.SessionKey)
        sess = s_key.get()
        if not sess:
            raise endpoints.NotFoundException(
                'No Session found with key: %s' % request.SessionKey)

        # Add to wishlist
        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        if not profile:
            raise endpoints.NotFoundException(
                'No profile found')

        # Check that the session does not already exist
        # Prevent the same session from being added to wishlist
        query = Wishlist.query(ancestor=p_key)
        query = query.filter(Wishlist.sessionKey == request.SessionKey)
        if len(query.fetch()) != 0:
            raise endpoints.BadRequestException(
                "That session is already in your wishlist")

        # generate Wishlist ID based on User ID
        w_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        w_key = ndb.Key(Wishlist, w_id, parent=p_key)

        # save new wishlist to datastore
        newWish = Wishlist(sessionKey=request.SessionKey)
        newWish.key = w_key
        newWish.put()

        return request

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      name="getSessionWishList")
    def getSessionWishList(self, request):
        """This function gets all wishlists of user."""
        # check for authentication
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # get Profile from datastore
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        if not profile:
            raise endpoints.NotFoundException(
                'No profile found')

        # Output all sessions in profile
        query = Wishlist.query(ancestor=p_key)
        query = query.fetch()

        slist = []
        for q in query:
            s_key = ndb.Key(urlsafe=q.sessionKey)
            slist.append(self._copySessionToForm(s_key.get()))

        return SessionForms(
            items=slist)

    @endpoints.method(WishListDelete, WishListDelete,
                      name='deleteSessionInWishlist')
    def deleteSessionInWishlist(self, request):
        """This function deletes specified wishlist of user"""
        # check for authentication
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # check for Wishlist key
        if not request.WishKey:
                raise endpoints.BadRequestException(
                    "'WishKey' field required")

        # Try and get the Wishlist object with Wishlist key
        w_key = ndb.Key(urlsafe=request.WishKey)
        wish = w_key.get()
        if not wish:
            raise endpoints.NotFoundException(
                'No Wishlist found with key: %s' % request.WishKey)

        # Check that user is ancestor of wishlist
        p_key = ndb.Key(Profile, user_id)
        if w_key.parent() != p_key:
            raise endpoints.BadRequestException("You don't own that wishlist")

        # delete the wishlist
        w_key.delete()

        return request


# - - - Additional Queries - - - - - - - - - - - - - - - - -

    @endpoints.method(message_types.VoidMessage, WebSafeKeys,
                      path='websafekeys', http_method='GET',
                      name='getWebSafeKeys')
    def getWebSafeKeys(self, request):
        """Get websafe keys for all conferences"""
        # Query all conferences for their websafe keys
        items = []
        query = Conference.query()
        for conf in query.fetch():
            temp = conf.key.parent().get()
            items.append([conf.name, conf.key.urlsafe(), temp.displayName])

        # Create and send message with all the keys, names, and organizers
        keys = []
        wsk = WebSafeKeys()
        q = WebSafeKeyQuery()
        for i in items:
            temp = WebSafeKeyQuery(name=i[0], key=i[1], organizer=i[2])
            keys.append(temp)
        wsk.items = keys
        wsk.check_initialized()
        return wsk

    @endpoints.method(message_types.VoidMessage, SessionKeys,
                      name='getSessionKeys')
    def getSessionKeys(self, request):
        """Get websafe keys for all sessions"""
        # Query all sessions for thier websafe keys
        items = []
        query = Session.query()
        for sess in query.fetch():
            items.append([sess.sessionName, sess.key.urlsafe()])

        # Create and send message with all keys and names
        keys = []
        wsk = SessionKeys()
        for i in items:
            temp = SessionKeyQuery(name=i[0], key=i[1])
            keys.append(temp)
        wsk.items = keys
        wsk.check_initialized()
        return wsk

    @endpoints.method(message_types.VoidMessage, SessionKeys,
                      name='getWishlists')
    def getWishlists(self, request):
        """Get all wishlists"""
        # Query all sessions for thier websafe keys
        items = []
        query = Wishlist.query()
        for wish in query.fetch():
            temp = wish.key.parent().get().displayName
            items.append([temp, wish.key.urlsafe()])

        # Create and send message with all keys and names
        keys = []
        wsk = SessionKeys()
        for i in items:
            temp = SessionKeyQuery(name=i[0], key=i[1])
            keys.append(temp)
        wsk.items = keys
        wsk.check_initialized()
        return wsk

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      name='getQueryProblem1')
    def getQueryProblem1(self, request):
        """One implementation of the Task 3 query related problem"""
        query = Session.query()
        query = query.filter(Session.typeOfSession != "WORKSHOP").fetch()
        sess = [x for x in query if x.startTime < 1900]
        return SessionForms(
            items=[self._copySessionToForm(s) for s in sess])

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      name='getQueryProblem2')
    def getQueryProblem2(self, request):
        """Another implementation of the Task 3 query related problem"""
        query = Session.query()
        query = query.filter(Session.startTime < 1900).fetch()
        sess = [x for x in query if x.typeOfSession != "WORKSHOP"]
        return SessionForms(
            items=[self._copySessionToForm(s) for s in sess])


# - - - Task Functions for getFeaturedSpeaker   - - - - - - -

    @staticmethod
    def _cacheSpeaker(sessionKey):
        """Create featured speaker and put in memcache
        used by SetFeaturedHandler"""

        print "In _cacheSpeaker"

        # Get key for session
        s_key = ndb.Key(urlsafe=sessionKey)
        sess = s_key.get()

        # See if the session exists
        if not sess:
            # fail silently
            temp = "Failed to find session for featured speaker"
            memcache.set(MEMCACHE_FEATURED_KEY, temp)
            return

        # get ancestor key
        c_key = s_key.parent()
        print "Got ancestor key"

        # get all sibling sessions
        allConfs = Session.query(ancestor=c_key)
        allConfs = allConfs.filter(Session.speaker == sess.speaker)
        print len(allConfs.fetch()), ": conferences"

        # Set featured speaker only if conditions are met
        if len(allConfs.fetch()) > 1:
            # Get all sesssion names
            print "FEATURED SPEAKER"
            temp = ""
            for i in allConfs:
                temp += i.sessionName
                temp += ", "
            temp = temp[:-2]  # remove the final comma and space
            # format featured speaker and set it in memcache
            announcement = FEATURED_TPL % sess.speaker
            announcement += temp
            memcache.set(MEMCACHE_FEATURED_KEY, announcement)

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Returns the contents of the memcache message
        for featured speaker"""
        return StringMessage(data=memcache.get(MEMCACHE_FEATURED_KEY) or "")


# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name,
                            getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore,
         creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or
                             "")


# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck)
                     for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId)
                      for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf,
                                              names[conf.organizerUserId])
                   for conf in conferences])

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='filterPlayground',
                      http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""
        q = Conference.query()
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)
        q = q.filter(Conference.city == "London")
        q = q.filter(Conference.topics == "Medical Innovations")
        q = q.filter(Conference.month == 6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )


api = endpoints.api_server([ConferenceApi])  # register API

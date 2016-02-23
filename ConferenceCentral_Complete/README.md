# Project 4 Conference Organization App

## Installation
The application is running at the following url:
https://udacity-conference-1209.appspot.com

Additionally the app can be run locally using the Conference_Central Complete directory with GoogleAppEngineLauncher

## Usage

### Access

To use the apis explorer with this application, use this url:
https://apis-explorer.appspot.com/apis-explorer/?base=https://udacity-conference-1209.appspot.com/_ah/api#p/conference/v1/

Additionally, if the project is running locally, it can be accessed at:
localhost:PORT#/_ah/api/explorer

where PORT# is the port that the app is running on locally

### Testing

Functions can be tested via the api explorer interface. By clicking on the request body field, properties can be added and specified. Some functions take an inbound VoidMessage type and do not need any properties to function. Because the front end interface is not yet specified, most path names have been left blank. In cases where the path has been specified, there may be additional fields in addition to the Request body field that take a url safe key. Otherwise, all properties will be specified in the Request body.

When required, url safe keys can be obtained from the datastore. The additional queries getWebSafeKeys(), getSessions(), and getWishlists() return a keys for all conferences, sessions, and wishlists respectively. These additional queries can be used to obtain url safe keys without needing to use the datastore.

## Limitations

There is no frontend support to these functions. Thus, except in obvious cases, the path variables for the endpoint methods have been intentionally left blank. In order to incorporate the new endpoints into a frontend, the blank path variables can be defined after fitting path names are decided.

## Task 1 Explaination of design choices

### Sessions

Sessions are defined thusly:
```
class Session(ndb.Model):
    """Session -- Session object"""
    sessionName     = ndb.StringProperty(required=True)
    highlights      = ndb.StringProperty()
    speaker         = ndb.StringProperty(required=True)
    duration        = ndb.IntegerProperty()
    typeOfSession   = ndb.StringProperty()
    date            = ndb.DateProperty()
    startTime       = ndb.IntegerProperty()
```

The sessionName, highlights, and typeOfSession properties are defined as strings as they will contain either one or more words. Duration and startTime are defined as integers. Duration is expected to be a value representing minutes. The startTime property is expected to be an integer value specifying the hour and minute time in 24 hour form (eg. 1730 for 5:30pm) as was specified. The date property is defined as a DateProperty() as representing a date requires a suitable data structure.

### Speakers

In this application, speakers are implemented as a string containing the speaker's name. This is because additional functionality will be needed to added to provide ways of identifying and creating indivudal speaker objects. Sometimes, a user may only know the name of the speaker and have no additional identifying information. Additionally, it is unlikely that different speakers have the exact same name.

## Task 2 Wishlist

Wishlist was added as an entity with a string field containing the url safe key of a session object. The Wishlist is always created with a user as an ancestor. This means that the owner of the wishlist can be quickly found via ancestor query. Defining a Wishlist in this way means that a user can easily store none or many small wishlist objects.

## Task 3 Additional Queries

### Indexes

Indexes were created by first running the application locally and then deploying to appspot

### Additional Queries

#### Get all the keys to conferences

The endpoints method getWebSafeKeys() queries all conferences and gets their web safe key, their name, and the name of the organizer. This is useful to access the conference keys and some basic info about each conference.

#### Get all the keys to sessions

The endpoints method getSessionKeys() queries all sessions and gets their web safe key and their name. This is useful to see all the sessions at once and to get their keys.

#### Get all the keys to wishlists

The endpoints method def getWishlists() queries all wish lists and reterns a web safe key and name for each one. This is useful when we want to see all the sessions that have been added to wishlists. 

#### Query problems

The functions getQueryProblem1 and getQueryProblem2 are implemented solutions to the query problems below

### Query related problem

Query restrictions:

1. An Inequality filter can only be applied to at most 1 property
startdate > 15th June && maxattendees < 1000 NOT VALID

2. A property with an inequality filter must be sorted first

The problem with this query is that we are applying inequality filters to two properties at once. This is the second of the restricted queries copied above for reference.

Possible solution 1:
Query all non workshops and use python to sort all before 7pm
Possible solution 2:
Query all sessions before 7pm, use python to get all non workshops
Both solutions worked when tested in api explorer. These are endpoint functions getQueryProblem1 and getQueryProblem2 respectively. Both appeared to work without issue. Times for both solutions to search through 8 sessions was between 300 - 400 ms.

## Task 4 Add a Task

On the creation of a session, a task is pushed into the task queue automatically. If there is more than one session of this speaker in the same conference, the featured speaker in the memcache is updated. The contents of the featured speaker can be accessed via the endpoints method: getFeaturedSpeaker()

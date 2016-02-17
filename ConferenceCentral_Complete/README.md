App Engine application for the Udacity training course.

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]

## Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
1. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
1. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
1. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
1. (Optional) Generate your client library(ies) with [the endpoints tool][6].
1. Deploy your application.


[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool

ud858
=====

Course code for Building Scalable Apps with Google App Engine in Python class

https://apis-explorer.appspot.com/apis-explorer/?base=https://udacity-conference-1209.appspot.com/_ah/api#p/conference/v1/

Task 1 Explain your design choices
Session name           A String
highlights             A String
speaker                Defined as a String because it will be difficult to identify individual speakers
duration              Integer containing hours
typeOfSession          A String that is stored and queried in all uppercase
date                   Date object
start time             4 digit integer showing time in 24 hour format as required


Task 2 Wishlist
Wishlist was added as a repeatable property in the Profile object. This is because this info is very much associated with the user.
Additionally many users may have empty wish lists so it does not make sense to create a wishlist object for each user when this object
may not be used.

Task 3 Solve the query related problem:
How to handle all non-workshop sessions before 7pm? 
1. An Inequality filter can only be applied to at most 1 property
startdate > 15th June && maxattendees < 1000 NOT VALID
2. A property with an inequality filter must be sorted first
Of the sessions, we are applying inequality filters to two properties at once. This is a restricted query.
Possible solution 1:
Query all non workshops and use python to sort all before 7pm
Possible solution 2:
Query all sessions before 7pm, use python to excise all workshops

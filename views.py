from flask import Flask, redirect, request, \
    render_template, url_for, flash, jsonify
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from models import Base, Category, CategoryItem, User
from flask import session as login_session
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import requests
import os
import hashlib


# Social Google Login settings below
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/userinfo.profile',
          'https://www.googleapis.com/auth/userinfo.email']
API_SERVICE_NAME = 'people'
API_VERSION = 'v1'


app = Flask(__name__)

engine = create_engine('sqlite:///catalog.db?check_same_thread=False')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Custom filter functions

def firstUpper(word):
    """If word's first letter Is not capital already
    then we capatilize it."""
    if not word[0].isupper():
        return word.capitalize()
    else:
        return word

app.jinja_env.filters['firstUpper'] = firstUpper


# Social Login functions below

@app.route('/authorize')
def authorize():
    if 'credentials' not in login_session:
        state = hashlib.sha256(os.urandom(1024)).hexdigest()
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, scopes=SCOPES, state=state
        )
        flow.redirect_uri = url_for('oauth2callback', _external=True)

        authorization_url, state = flow.authorization_url(
            # Enable offline access so that you can \
            # refresh an access token without
            access_type='offline',
            # re-prompting the user for permission. \
            # Recommended for web server apps.
            # Enable incremental authorization. Recommended as a best practice.
            include_granted_scopes='true')

        # Store the state so the callback can verify the auth server response.
        login_session['state'] = state

        return redirect(authorization_url)
    return redirect(url_for('index'))


@app.route('/oauth2callback')
def oauth2callback():
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = login_session['state']

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = request.url
    print(authorization_response)
    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    # credentials in a persistent database instead.
    credentials = flow.credentials
    login_session['credentials'] = credentials_to_dict(credentials)
    userinfo_url = 'https://www.googleapis.com/plus/v1/people/me'
    headers = {
        'Authorization': 'Bearer {0}'
        .format(login_session['credentials']['token']),
        'Accept': 'application/json'}
    userinfo = requests.get(userinfo_url, headers=headers)
    response = userinfo.json()
    login_session['userid'] = response['id']
    login_session['username'] = response['displayName']
    login_session['picture'] = response['image']['url']
    login_session['email'] = response['emails'][0]['value']

    # see if user exists, if it doesn't create a new user
    user_id = getUserID(login_session['email'])
    if not user_id:
        print("Creating new User")
        user_id = createUser(login_session)
    login_session['userid'] = user_id
    flash("Login Successful")
    return redirect(url_for("index"))


def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
        }


@app.route('/revoke')
def revoke():
    """revoke credentials and logout"""
    if 'credentials' not in login_session:
        return ('You need to <a href="/authorize">Login first</a> \
        before ' + 'to revoke credentials and logout')

    credentials = google.oauth2.credentials.Credentials(
        **login_session['credentials'])

    revoke = requests.post(
        'https://accounts.google.com/o/oauth2/revoke',
        params={'token': credentials.token},
        headers={'content-type': 'application/x-www-form-urlencoded'})

    status_code = getattr(revoke, 'status_code')
    if status_code == 200:
        return clear_credentials()
    else:
        return('An error occurred.')


@app.route('/clear')
def clear_credentials():
    """Clear all the credentials from the session"""
    if 'credentials' in login_session:
        del login_session['credentials']
        del login_session['username']
        del login_session['userid']
        del login_session['picture']
        del login_session['email']
    flash("Logout Successful")
    return redirect(url_for("index"))


# Json Api endpoint Functions
@app.route('/catalog.json')
def catalogJson():
    categories = categories_list()
    return jsonify(Category=[i.serializeCatalog for i in categories])


@app.route('/catalog/categories/JSON')
def categoryJSON():
    categories = categories_list()
    return jsonify(Categories=[i.serializeCategory for i in categories])


@app.route("/catalog/<category>/items/JSON")
def categoryItemsJson(category):
    category_obj = CategoryByTitle(category_title=category)
    items = category_obj.serializeCategoryItems
    return jsonify(CategoryItems=items)


@app.route("/catalog/<category>/<item>/JSON")
def categoryItemJSON(category, item):
    category_obj = CategoryByTitle(category_title=category)
    item_obj = itemWithCategory(item_title=item, category_obj=category_obj)
    if item_obj:
        return jsonify(CategoryItem=item_obj.serializeCategoryItem)
    else:
        return "Not Exists"

# Catalog functions below


def categories_list():
    """Returns list of Categories"""
    categories = session.query(Category).order_by(Category.title)
    return categories


def CategoryByTitle(category_title=None):
    """Get Category by title"""
    return session.query(Category).filter_by(title=category_title).first()


def itemWithCategory(item_title=None, category_obj=None):
    """Function to retrive a item by given item name and category object"""
    return session.query(CategoryItem).filter_by(
        title=item_title,
        category=category_obj).first()


@app.route('/login')
def login():
    """renders login template"""
    return render_template('login.html', categories=categories_list())


@app.route('/')
def index():
    """Show both categories and latest items list"""
    categories = categories_list()
    items = session.query(CategoryItem).order_by(CategoryItem.id.desc())
    return render_template("index.html", categories=categories, items=items)


@app.route('/catalog/<category>/items')
def categoryItems(category):
    """Show list of items of a specific category"""
    category_obj = CategoryByTitle(category_title=category)
    items = category_obj.categoryitems
    return render_template(
        'categoryitems.html',
        items=items,
        categories=categories_list(),
        category=category_obj.title)


@app.route('/catalog/<category>/<item>')
def categoryItem(category, item):
    """Show Item Info"""
    category_obj = CategoryByTitle(category_title=category)
    item_obj = itemWithCategory(item_title=item, category_obj=category_obj)
    return render_template(
        "iteminfo.html",
        item=item_obj,
        categories=categories_list())


@app.route('/catalog/item/new', methods=['GET', 'POST'])
def createItem():
    """Create Item"""
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == "POST":
        category = session.query(Category).filter_by(
            title=request.form['category']).first()
        if request.form['title']:
            # checks whether given item exists in the \
            # given category
            if session.query(CategoryItem).filter(func.lower(
                    CategoryItem.title) == func.lower(request.form['title']),
                    CategoryItem.category == category).first() is None:

                user_obj = getUserInfo(login_session['userid'])
                item = CategoryItem(
                    title=request.form['title'],
                    description=request.form['description'],
                    category=category, user=user_obj)
                session.add(item)
                session.commit()
                flash("New Item Created")
                return redirect(url_for(
                    "categoryItems",
                    category=category.title))
            else:
                flash(
                    "Item already exists In the \
                    Category, try adding another Item")
                return render_template(
                    "newitem.html",
                    categories=categories_list())
    else:
        return render_template("newitem.html", categories=categories_list())


@app.route('/catalog/<category>/<item>/edit', methods=['GET', 'POST'])
def editItem(category, item):
    """Edit Item """
    if 'username' not in login_session:
        return redirect('/login')
    category_obj = CategoryByTitle(category_title=category)
    item_obj = itemWithCategory(item_title=item, category_obj=category_obj)
    if login_session['userid'] != item_obj.user.id:
        return "You are not authorized to edit this Item"
    if request.method == "POST":
        if request.form['title']:
            item_obj.title = request.form['title']
        if request.form['description']:
            item_obj.description = request.form['description']
        if request.form['category']:
            new_category = CategoryByTitle(
                category_title=request.form['category'])
            # checks If a Item with such new category already exists, \
            # If not then change to a new category.
            if session.query(CategoryItem).filter(
                    func.lower(CategoryItem.title) == func.lower(item),
                    CategoryItem.category == new_category).first() is None:
                item_obj.category = new_category
        session.add(item_obj)
        session.commit()
        flash("Item Edited sucessfully")
        return redirect(url_for(
            "categoryItem", category=new_category.title,
            item=item_obj.title))
    else:
        return render_template(
            "edititem.html",
            item_obj=item_obj,
            categories=categories_list())


@app.route('/catalog/<category>/<item>/delete', methods=['GET', 'POST'])
def deleteItem(category, item):
    """Delete Item"""
    if 'username' not in login_session:
        return redirect('/login')
    category_obj = CategoryByTitle(category_title=category)
    itemToDelete = itemWithCategory(item_title=item, category_obj=category_obj)
    if login_session['userid'] != itemToDelete.user.id:
        return "Your are not Authorized to delete, create your own"
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Item deleted successfully')
        return redirect(url_for("categoryItems", category=category_obj.title))
    else:
        return render_template("deleteitem.html", item=itemToDelete)


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


def createUser(login_session):
    newUser = User(
        name=login_session['username'],
        email=login_session['email'],
        picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
    app.config["JSON_SORT_KEYS"] = False
    app.debug = False
    app.run(host='0.0.0.0', port=5000)

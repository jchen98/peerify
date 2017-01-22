from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import gettempdir
from flask import jsonify
from functools import wraps
from flask_mail import Mail, Message
import json
import mailer
import os
import sqlalchemy

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response


# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = gettempdir()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# add mailserver to flask
app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'peerifybot@gmail.com'
app.config['MAIL_PASSWORD'] = 'cs50peerify'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)


# configure CS50 Library to use SQLite database
db = SQL("sqlite:///users.db")

class SQL(object):
    def __init__(self, url):
        try:
            self.engine = sqlalchemy.create_engine(url)
        except Exception as e:
            raise RuntimeError(e)
    def execute(self, text, *multiparams, **params):
        try:
            statement = sqlalchemy.text(text).bindparams(*multiparams, **params)
            result = self.engine.execute(str(statement.compile(compile_kwargs={"literal_binds": True})))
            # SELECT
            if result.returns_rows:
                rows = result.fetchall()
                return [dict(row) for row in rows]
            # INSERT
            elif result.lastrowid is not None:
                return result.lastrowid
            # DELETE, UPDATE
            else:
                return result.rowcount
        except sqlalchemy.exc.IntegrityError:
            return None
        except Exception as e:
            raise RuntimeError(e)

def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/0.11/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


#  ***************************************** Register and Login *****************************************************
@app.route("/")
def main():
    """Home page."""
    return render_template("main.html")

@app.route("/about")
def about_us():
    """About us page."""
    return render_template("about_us.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""

    if request.method == "POST":

        # queries database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # checks if username is available
        if not request.form.get("username") or len(rows) == 1:
            return render_template("apology.html", apology="This email is already taken. Please try a different email address.")

        # encrypts password
        hash = pwd_context.encrypt(request.form.get("password"))

        #gets initials of registered user from full name (users who match with each other and swap essays will be able to see each others' initials)
        name = request.form.get("name")
        initial = "";
        if not name[0] == " ":
                initial += name[0].upper() + ". "
        # iterates through each char of name, retrieving rest of initial
        for c in range (2, len(name)):
            if name[c-1] == " ":
                initial += name[c].upper() + ". "

        # adds username and hashed password into database
        user = db.execute("INSERT INTO users (name, username, hash, initial) VALUES(:name, :username, :password, :initial)", name=request.form["name"], username=request.form["username"], password=hash, initial = initial)

        # redirects user to home page
        return redirect(url_for("index"))

    # GET request - returns the register page
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        #form validation already done through Javascript on client side.

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return render_template("apology.html", apology="Invalid username and/or password.")

        #stores user info in session to be called when needed
        session["user_id"] = rows[0]["id"]
        session["user_email"] = rows[0]["username"]

        #redirects user to home page (main) after login
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    #clears user_id and email address from session
    session.clear()

    # redirect user to login form
    return redirect(url_for("main"))

@app.route("/home")
@login_required
def index():
    """Index for user accounts."""

    # queries for all essays submitted by user
    essays = db.execute("SELECT * FROM essays WHERE id=:user_id", user_id=session.get("user_id"))

    # number of user's essay entries
    essay_number = len(essays)

    """ Checks if feedback is available for essays """

    # queries for all of user's essay_id
    essay_id = db.execute("SELECT essay_id FROM essays WHERE id=:user_id", user_id=session.get("user_id"))

    # queries for all of the essay_id in annotations table
    annotations_essay_id = db.execute("SELECT essay_id FROM annotations")

    # appends all the annotations id into one list for comparison in the next for loop
    annotations_id = []
    for i in range(len(annotations_essay_id)):
        annotations_id.append(annotations_essay_id[i]['essay_id'])

    # checks if any annotations are available for each of user's essays
    for i in range(len(essay_id)):
        if essay_id[i]['essay_id'] in annotations_id:
            # if annotations are available, update "feedback" from "pending" to "available"
            db.execute("UPDATE essays SET feedback = :feedback WHERE essay_id = :essay_id", feedback = "Available", essay_id = essay_id[i]['essay_id'])

    return render_template("index.html", essays=essays, essay_number=essay_number)

#  ***************************************** Upload Essays *****************************************************

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """ Upload essays in database."""
    if request.method == "POST":

        # enters uploaded essay into database table 'essays'
        db.execute("INSERT INTO essays (id, text, feedback) VALUES(:user_id, :essay_text, :feedback)", user_id=session.get("user_id"), essay_text=request.form.get("essay_text"), feedback="Pending")

        # redirects user to upload survey form
        return render_template("upload_form.html")

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("upload.html")

@app.route("/upload/form", methods=["POST"])
@login_required
def upload_form():
    """Upload details about essay, sends confirmation email, attempts to pair essay with peer if possible."""

    #finds the essay_id of current essay being uploaded in last page upload (should be max(essay_id)
    essay_id = db.execute("SELECT MAX(essay_id) from essays")[0]['MAX(essay_id)']

    #updates essay details for that essay
    db.execute("UPDATE essays SET date=:date, topic=:topic WHERE essay_id=:essay_id",
    date=request.form.get('date'), topic=request.form.get("user_category"), essay_id=essay_id)

    # sends confirmation email upon essay submission with information about received essay
    essay_text = db.execute("SELECT text FROM essays WHERE essay_id = :essay_id", essay_id = essay_id)[0]['text']
    mailer.sendConfirmationEmail(mail, session["user_email"], request.form.get('date'), request.form.get('user_category'), essay_text)

    """ Essay Pairing Algorithm """
    """Attemps to pair submitted essay with current unpaired essay in database -- otherwise, essay is just added as a new unpaired essay
    Paired based on same topic of essay. If paired, then your pair_essay_id is their essay_id, and vice versa. Your pair_id is their user_id, and vice versa."""
    essay_topic = request.form.get("user_category")
    # queries the database - finds unpaired essays that have the same category and order by date of requested return (earliest first)
    unpaired_essays = db.execute("SELECT essay_id FROM essays WHERE topic=:essay_topic AND peer_id IS NULL ORDER BY date ASC", essay_topic = essay_topic)
    #essay that was just submitted will be in unpaired_essays by default. if there is another essay, we can pair with that one.
    #otherwise, if only that essay is in unpaired_essays, then keep that essay unpaired (wait for another essay to come through to pair w/ it)

    if len(unpaired_essays) > 1:
        matched_essay_id = unpaired_essays[0]["essay_id"] #essay_id of the essay that needs to be read first (that you're paired with)

        #edge case where the earliest due essay (first element in unpaired_essays) is still the essay you just submitted.
        if matched_essay_id == essay_id:
            matched_essay_id = unpaired_essays[1]["essay_id"]

        #user_id of the user who submitted the essay you're reading
        matched_id = db.execute("SELECT id FROM essays WHERE essay_id = :matched_essay_id", matched_essay_id = matched_essay_id)[0]["id"]
        #set your peer_essay_id to their essay_id, and your peer_id to their user_id
        db.execute("UPDATE essays SET peer_essay_id=:matched_essay_id, peer_id = :matched_id WHERE essay_id=:essay_id", matched_essay_id = matched_essay_id, matched_id = matched_id, essay_id = essay_id)
        #set their peer_essay_id to your essay_id, and their peer_id to your user_id
        db.execute("UPDATE essays SET peer_essay_id = :essay_id, peer_id=:user_id WHERE essay_id=:matched_essay_id", essay_id = essay_id, user_id = session["user_id"], matched_essay_id = matched_essay_id)

        #send emails to both users letting them know that they were paired
        #matched email takes matched_essay_id and retrieves email address (username)
        matched_email = db.execute("SELECT username FROM users WHERE id=:user_id", user_id = matched_id)[0]["username"]
        your_deadline = db.execute("SELECT date FROM essays WHERE essay_id = :essay_id", essay_id = matched_essay_id)[0]["date"]
        matched_user_deadline = db.execute("SELECT date FROM essays WHERE essay_id = :essay_id", essay_id =  essay_id)[0]["date"]
        mailer.sendPairingEmail(mail, session["user_email"], essay_topic, your_deadline)
        mailer.sendPairingEmail(mail, matched_email, essay_topic, matched_user_deadline)

        # queries for the text of the peer's essay (matched_essay_id) to display
        matched_text = db.execute("SELECT text FROM essays WHERE essay_id=:essay_id", essay_id=matched_essay_id)
        return render_template("paired.html")
    else:
        return render_template("unpaired.html", essay_topic = essay_topic)

    return render_template("submitted.html")



@app.route("/essays")
@login_required
def essays():
    """ Displays user's uploaded essays."""

    # gets the essay_id from link address
    essay_number = request.args.get('number')

    # queries for the text of associated essay_id
    essay_text = db.execute("SELECT text FROM essays WHERE essay_id = :essay_id", essay_id=essay_number)

    return render_template("essays.html", essay_text=essay_text[0]['text'])

#  ***************************************** Peer Essays *****************************************************

@app.route("/tasks")
@login_required
def tasks():
    """ Displays a list of matched essays of peer."""

    # queries all essays where user_id = peer_id
    matched_essays = db.execute("SELECT * FROM essays WHERE peer_id=:user_id", user_id=session.get("user_id"))

    # finds number of essays matched with the user
    essay_number = len(matched_essays)

    return render_template("tasks.html", matched_essays=matched_essays, essay_number=essay_number)


@app.route("/essays/peer")
@login_required
def peer_essays():
    """ Displays a specific matched essay of peer."""

    # gets the essay_id from link address
    essay_number = request.args.get('number')

    # queries for the essay text associated with essay_id
    essay_text = db.execute("SELECT text FROM essays WHERE essay_id = :essay_id", essay_id=essay_number)

    return render_template("peer_essays.html", essay_text=essay_text[0]['text'])


#  ***************************************** Messages *****************************************************

@app.route("/messages")
@login_required
def messages():
    """ Displays messages for user's essays and matched essays of peers."""

    # queries for all essays submitted by user
    essays = db.execute("SELECT * FROM essays WHERE id=:user_id", user_id=session.get("user_id"))

    # number of user's essay entries
    essay_number = len(essays)

    # queries for all essays where user_id = peer_id
    matched_essays = db.execute("SELECT * FROM essays WHERE peer_id=:user_id", user_id=session.get("user_id"))

    # finds length of matched_essays
    matched_essays_number = len(matched_essays)

    return render_template("messages.html", essay_number=essay_number, essays=essays, matched_essays=matched_essays, matched_essays_number=matched_essays_number)

@app.route("/messagelog", methods =["GET", "POST"])
@login_required
def message_log():
    """ Displays message log for one specific selected essay."""
    if request.method == "GET":
        essay_id_value = request.args.get('number')

        # queries for the essay_id of essays
        essay_id = db.execute("SELECT essay_id from essays WHERE id=:user_id", user_id=session.get("user_id"))

        # SQL: Get all the rows where essay_id = essay_id_value
        comments = db.execute("SELECT * from messages WHERE essay_id=:essay_id_value ORDER BY datetime ASC", essay_id_value=essay_id_value)

        # finds length of the SQL queries for iterations in jinja templating
        messages_length = len(comments)

        return render_template("messagelog.html", essay_id_value=essay_id_value, messages_length=messages_length, comments=comments)
    else:

        initials = db.execute("SELECT initial from users WHERE id=:user_id", user_id=session.get("user_id"))

        # enters comment into database table 'messages'
        db.execute("INSERT INTO messages (id, essay_id, message, initial) VALUES(:user_id, :essay_id, :message, :initial)",
        user_id=session.get("user_id"), essay_id=request.form.get("essay_id_value"), message=request.form.get("essay_text"), initial=initials[0]['initial'])

        #queries for the essay_id of essays
        essay_id = db.execute("SELECT essay_id from essays WHERE id=:user_id", user_id=session.get("user_id"))

        essay_id_value = request.form.get("essay_id_value")


        # SQL: Get all the rows where essay_id = essay_id_value
        comments = db.execute("SELECT * from messages WHERE essay_id=:essay_id_value ORDER BY datetime ASC", essay_id_value=essay_id_value)

        # finds length of the SQL queries for jinja
        messages_length = len(comments)

        return render_template("messagelog.html", essay_id_value=essay_id_value, messages_length=messages_length, comments=comments)

#  ***************************************** Account Settings *****************************************************

@app.route("/account")
@login_required
def account():
    """ User's account settings."""

    # queries for name of user
    name = db.execute("SELECT name FROM users WHERE id=:user_id", user_id=session.get("user_id"))

    return render_template("account.html", name=name[0]['name'])


@app.route("/password", methods =["GET", "POST"])
@login_required
def password():
    """ Enables users to change passwords."""
    if request.method == "POST":

        #confirm that user has entered a password into form
        if not request.form.get("curr_password"):
            return render_template("apology.html", apology="Enter a password.")

        elif not request.form.get("new_password"):
            return render_template("apology.html", apology="Enter a password.")

        elif not request.form.get("new_password_again"):
            return render_template("apology.html", apology="Enter a password.")

        #select user's session from the database users
        user_info = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session.get("user_id"))

        # checks if entered new passwords match
        if request.form.get("new_password") == request.form.get("new_password_again"):
            # hashes the new password
            hash_pw = pwd_context.encrypt(request.form["new_password"])
            db.execute("UPDATE users SET hash = :new_password WHERE id = :user_id", new_password=hash_pw, user_id=session.get("user_id"))
        else:
            return render_template("apology.html", apology="Passwords do not match.")

        #redirect to account page
        return redirect(url_for("account"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("password.html")



#  ***************************************** Annotatorjs Library *****************************************************
# Source: http://annotatorjs.org/
# Documentation Help for Implementation: https://blog.yipl.com.np/annotating-content-with-annotatorjs-in-webpages-2dbcaebbdf29#.a5r4sfnyy

@app.route("/annotation/store", methods = ["GET", "POST"])
@login_required
def annotation():
    """ Creates annotation."""
    # when user creates annotation, a JSON is created; JSON includes range of highlighted text, highlighted text, and essay_id
    json_info = request.get_json()

    # converts JSON dictionary into a string for database storage
    json_string = json.dumps(json_info)

    # inserts corresponding essay_id into database
    essay_id = json_info.get("page")

    # enters json_string into table "annotations"
    db.execute("INSERT INTO annotations (json_string, essay_id) VALUES(:json_string, :essay_id)", json_string=json_string, essay_id=essay_id)

    # creating the return value according to the Documentation instructions
    json_list = []
    json_list.append(json_string)

    if (request.get_json()):
        return_dict = {'status': 'success', 'id': json_list}
        return(json.dumps(return_dict))
    else:
        return_dict = {'status': 'error'}
        return(json.dumps(return_dict))

@app.route("/annotation/update/<id>", methods = ["GET", "POST"])
@login_required
def update(id):
    """ Updates annotations."""
    return("update")

@app.route("/annotation/delete/<id>", methods = ["GET", "POST", "DELETE"])
@login_required
def delete(id):
    """ Deletees annotations."""
    return("delete")

@app.route("/annotation/search", methods = ["GET", "POST"])
@login_required
def search():
    """ Searches for and loads annotations of essay """

    # gets the essay_id in the query string
    essay_id = request.args.get("page")

    # queries for all annotations associated with essay_id in database
    json_strings = db.execute("SELECT json_string FROM annotations WHERE essay_id = :essay_id", essay_id=essay_id)

    # number of comments associated with essay_id
    length = len(json_strings)

    # initializes an empty list
    json_list = []

    # appends every annotation into json_list
    for i in range(len(json_strings)):
        json_text = json_strings[i].get('json_string')
        json_list.append(json.loads(json_text))

    # documentation indicates that return values must include length of JSON and JSON itself
    return_dict = {'total': length, 'rows': json_list}

    return(json.dumps(return_dict))


if __name__ == '__main__':
 app.debug = True
 port = int(os.environ.get("PORT", 5000))
 app.run(host='0.0.0.0', port=port)

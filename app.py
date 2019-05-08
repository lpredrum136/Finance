import os, datetime, re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Select cash amount left from user table. This will be the second last row of the table
    user = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    cash = user[0]["cash"]
    # Start calculating total value of one's portfolio. This will be the last row
    totalValue = cash
    # Update price and TOTAL
    rows = db.execute("SELECT symbol, name, SUM(shares), price, total FROM portfolio where id = :id GROUP BY symbol",\
                        id=session["user_id"])
    # Delete all records with SUM(shares) == 0
    for row in rows:
        if row["SUM(shares)"] == 0:
            db.execute("DELETE FROM portfolio WHERE symbol = :symbol", symbol=row["symbol"])
        else:
            quote = lookup(row["symbol"])
            price = quote["price"]
            db.execute("UPDATE portfolio SET price = :price, total = :total WHERE id = :id AND symbol = :symbol",\
                        price=usd(price), total=usd(price*row["SUM(shares)"]), id=session["user_id"], symbol=row["symbol"])
            totalValue += price * row["SUM(shares)"] # Update the total value at the same time
    # Select rows in database
    rows = db.execute("SELECT symbol, name, SUM(shares), price, total FROM portfolio WHERE id = :id GROUP BY symbol",\
                        id=session["user_id"])
    # Result
    return render_template("portfolio.html", rows=rows, cash=usd(cash), totalValue=usd(totalValue))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    elif request.method == "POST":
        # Check validity
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        quote = lookup(symbol)
        if not symbol or not quote:
            return apology("Symbol missing or invalid")
        if not shares:
            return apology("Number of shares not provided")
        if shares == 0:
            return redirect("/")
        # Select the cash
        rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        # Calculate balance after buying
        debit = quote["price"] * int(shares)
        balance = rows[0]["cash"] - debit
        # Validate balance
        if balance < 0:
            return apology("Not enough money")
        # Update cash balance
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=balance, id=session["user_id"])
        # Update purchase history
        id = session["user_id"]
        name = quote["name"]
        price = quote["price"]
        now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        db.execute("INSERT INTO history (id, name, symbol, shares, price, debit, balance, datetime)\
                    VALUES (:id, :name, :symbol, :shares, :price, :debit, :balance, :datetime)",\
                    id=id, name=name, symbol=symbol, shares=shares, price=usd(price), debit=usd(debit), balance=usd(balance),\
                    datetime=now)
        # Add and update portfolio
        db.execute("INSERT INTO portfolio (id, symbol, name, shares) VALUES (:id, :symbol, :name, :shares)",\
                    id=id, symbol=symbol, name=name, shares=shares)
        # Return results
        return redirect("/")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT name, symbol, shares, price, debit, credit, balance, datetime FROM history WHERE id = :id",\
                    id=session["user_id"])
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    elif request.method == "POST":
        # Get and validate info
        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("Must input symbol")
        # Look up quote
        quoted = lookup(symbol)
        if not quoted:
            return apology("Invalid symbol")
        quotedInUsd = usd(quoted["price"])
        # Result
        return render_template("quoted.html", quoted=quoted, quotedInUsd=quotedInUsd)
        

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    elif request.method == "POST":
        # Get info
        username = request.form.get("username")
        password = request.form.get("password")
        if len(password) < 8:
            return apology("Password must be >= 8 characters")
        elif re.search('[0-9]', password) is None:
            return apology("Password must have at least a number")
        elif re.search('[A-Z]', password) is None: 
            return apology("Password must have at least a capital letter")
        confirmation = request.form.get("confirmation")
        passwordHash = generate_password_hash(password)
        # Validate info
        if not username or not password or not confirmation:
            return apology("Please provide username and/or password")
        if password != confirmation:
            return apology("Password confirmation does not match")
        # Add info to database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=passwordHash)
        return redirect("/")

@app.route("/changepassword", methods=["GET", "POST"])
@login_required
def changePassword():
    """Change password"""
    if request.method == "GET":
        return render_template("changepw.html")
    if request.method == "POST":
        # Get info
        password = request.form.get("password")
        newPassword = request.form.get("newPassword")
        confirmation = request.form.get("confirmation")
        # Validate info
        if not password or not newPassword or not confirmation:
            return apology("Must input info")
        # Validate password criteria
        if len(newPassword) < 8:
            return apology("Password must be >= 8 characters")
        elif re.search('[0-9]', newPassword) is None:
            return apology("Password must have at least a number")
        elif re.search('[A-Z]', newPassword) is None: 
            return apology("Password must have at least a capital letter")
        # Validate old password match
        rows = db.execute("SELECT hash FROM users WHERE id = :id", id=session["user_id"])
        if not check_password_hash(rows[0]["hash"], password):
            return apology("wrong old password", 403)
        # Validate new password match
        if newPassword != confirmation:
            return apology("New password confirmation does not match")
        # Update password
        db.execute("UPDATE users SET hash = :hash WHERE id = :id",\
                    hash=generate_password_hash(newPassword), id=session["user_id"])
        return redirect("/")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        # Get the portfolio
        rows = db.execute("SELECT symbol, name, SUM(shares) FROM portfolio WHERE id = :id GROUP BY symbol", id=session["user_id"])
        return render_template("sell.html", rows=rows)
    elif request.method == "POST":
        # Check usual validity
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        if not symbol:
            return apology("Symbol missing or invalid")
        if shares == 0:
            return redirect("/")
        # Check if user wants to sell more than he has
        rows = db.execute("SELECT SUM(shares) FROM portfolio WHERE id = :id AND symbol = :symbol",\
                            id=session["user_id"], symbol=symbol)
        if shares > rows[0]["SUM(shares)"]:
            return apology("Trying to sell more than you have")
        # Select the cash
        rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        # Calculate balance after buying
        quote = lookup(symbol)
        credit = quote["price"] * int(shares)
        balance = rows[0]["cash"] + credit
        # Update cash balance
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=balance, id=session["user_id"])
        # Update purchase history
        id = session["user_id"]
        name = quote["name"]
        price = quote["price"]
        now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        db.execute("INSERT INTO history (id, name, symbol, shares, price, credit, balance, datetime)\
                    VALUES (:id, :name, :symbol, :shares, :price, :credit, :balance, :datetime)",\
                    id=id, name=name, symbol=symbol, shares=0-shares, price=usd(price), credit=usd(credit), balance=usd(balance),\
                    datetime=now)
        # Add and update portfolio
        db.execute("INSERT INTO portfolio (id, symbol, name, shares) VALUES (:id, :symbol, :name, :shares)",\
                    id=id, symbol=symbol, name=name, shares=0-shares)
        # Return results
        return redirect("/")

@app.route("/addfund", methods=["GET", "POST"])
@login_required
def addfund():
    """Add fund"""
    # Get info
    if request.method == "GET":
        return render_template("addfund.html")
    if request.method == "POST":
        fund = float(request.form.get("fund"))
        # Validate info
        if not fund:
            return apology("Must specify amount")
        # Select old cash
        rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=rows[0]["cash"]+fund, id=session["user_id"])
        return redirect("/")

@app.route("/buyandsell", methods=["GET", "POST"])
@login_required
def buyandsell():
    """Buy and sell straight from main page(portfolio)"""
    # Get info
    if request.method == "GET":
        return redirect("/")
    if request.method == "POST":
        for item in request.form: # For each "input name" in the html "form"
            command = request.form.get(item) # Get the command: buy or sell?
            # If buy
            if command == "buy":
                # Select the cash
                rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
                # Calculate balance after buying
                quote = lookup(item)
                symbol = quote["symbol"]
                name = quote["name"]
                price = quote["price"]
                shares = request.form.get(f"shares{item}")
                debit = price * int(shares)
                balance = rows[0]["cash"] - debit
                # Validate balance
                if balance < 0:
                    return apology("Not enough money")
                # Update cash balance
                db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=balance, id=session["user_id"])
                # Update purchase history
                now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')
                db.execute("INSERT INTO history (id, name, symbol, shares, price, debit, balance, datetime)\
                            VALUES (:id, :name, :symbol, :shares, :price, :debit, :balance, :datetime)",\
                            id=session["user_id"], name=name, symbol=symbol, shares=shares, price=usd(price),\
                            debit=usd(debit), balance=usd(balance), datetime=now)
                # Add and update portfolio
                db.execute("INSERT INTO portfolio (id, symbol, name, shares) VALUES (:id, :symbol, :name, :shares)",\
                            id=session["user_id"], symbol=symbol, name=name, shares=shares)
            if command == "sell":
                # Calculate balance after buying
                quote = lookup(item)
                symbol = quote["symbol"]
                name = quote["name"]
                price = quote["price"]
                shares = int(request.form.get(f"shares{item}"))
                # Check if user wants to sell more than he has
                rows = db.execute("SELECT SUM(shares) FROM portfolio WHERE id = :id AND symbol = :symbol",\
                                    id=session["user_id"], symbol=symbol)
                if shares > rows[0]["SUM(shares)"]:
                    return apology("Trying to sell more than you have")
                # Select the cash
                rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
                credit = price * shares
                balance = rows[0]["cash"] + credit
                # Update cash balance
                db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=balance, id=session["user_id"])
                # Update purchase history
                now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')
                db.execute("INSERT INTO history (id, name, symbol, shares, price, credit, balance, datetime)\
                            VALUES (:id, :name, :symbol, :shares, :price, :credit, :balance, :datetime)",\
                            id=session["user_id"], name=name, symbol=symbol, shares=0-shares, price=usd(price),\
                            credit=usd(credit), balance=usd(balance), datetime=now)
                # Add and update portfolio
                db.execute("INSERT INTO portfolio (id, symbol, name, shares) VALUES (:id, :symbol, :name, :shares)",\
                            id=session["user_id"], symbol=symbol, name=name, shares=0-shares)
                """ # Return results
                return f"{symbol}, {command}, {name}, {price}, {shares}, {debit}, {balance}" """
        return redirect("/")   

def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
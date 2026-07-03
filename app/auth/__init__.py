from app.auth.passport import Passport
from app.auth.strategies.google import GoogleStrategy
from app.auth.strategies.jwt import JWTStrategy
from app.auth.strategies.local import LocalStrategy
from app.auth.strategies.register import RegisterStrategy

passport = Passport()
passport.use("jwt", JWTStrategy())
passport.use("local", LocalStrategy())
passport.use("register", RegisterStrategy())
passport.use("google", GoogleStrategy())

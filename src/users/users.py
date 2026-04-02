import json
import os
from typing import Union
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import jwt
#import passlib
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from fastapi import HTTPException, status

class Accounts:
    def __init__(self):

        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.accounts = {}

        self.userFile = os.getenv('DATABOARD_USERFILE')
        os.makedirs(os.path.dirname(self.userFile), exist_ok=True)
        if os.path.exists(self.userFile):
            with open(self.userFile) as f:
                self.accounts = json.load(f)

    # --------- Internal-only methods ---------
    def saveUsers(self):
        """Persist current users to the JSON file."""
        with open(self.userFile, "w") as f:
            json.dump(self.accounts, f, indent=2)


    def getUser(self, username: str) -> Union["User", None]:
        """Return internal user (with password hash)."""
        user_dict = self.accounts.get(username)
        if user_dict is not None:
            return User(**user_dict)

    def authUser(self, username: str, password: str) -> Union["User", bool]:
        """Authenticate user using password hash."""
        user = self.getUser(username)
        if not user:
            return False
        if not self.pwd_context.verify(password, user.password):
           return False
        return user

    def hashPassword(self, password: str):
        return self.pwd_context.hash(password)

    def getSecretKey(self):
        return os.getenv('DATABOARD_SECRET_KEY', 'PROVIDEARANDOMSTRINGINTHEENVIRONMENT')

    def getAlgorithm(self):
        return os.getenv('DATABOARD_SECRET_ALGORITHM', 'HS256')

    def getExpires(self):
        """
        Return the token expiration time, defaults to 1 day

        :return:
        """
        return os.getenv('DATABOARD_SECRET_EXPIRES', 60 * 24)

    def getCurrentUser(self, token):
        """
        Get the current user by a JWT

        :param token:
        :return:
        """
        credException = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt.decode(token, self.getSecretKey(), algorithms=[self.getAlgorithm()])
            username: str = payload.get("sub")
            if username is None:
                raise credException
            token_data = TokenData(username=username, version=payload.get("version"))
        except InvalidTokenError:
            raise credException

        user = self.getUser(username=token_data.username)
        if user is None:
            raise credException
        if user.tokenVersion != token_data.version:
            raise credException

        return user


    def createAccessToken(self, data: dict, expires_delta: Union[timedelta, None] = None):
        """
        Create an access token

        :param data:
        :param expires_delta:
        :return:
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
            to_encode.update({"exp": expire})

        encoded_jwt = jwt.encode(
            to_encode,
            self.getSecretKey(),
            algorithm=self.getAlgorithm()
        )
        return encoded_jwt

    def getAccessToken(self, form_data):
        """
        Create an access token by logging in

        :param form_data:
        :return:
        """
        user = self.authUser(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = self.createAccessToken(
            data={"sub": user.username, "version": user.tokenVersion},
            expires_delta= timedelta(minutes=self.getExpires()) if user.tokenExpires else None
        )
        return Token(access_token=access_token, token_type="bearer")

    # --------- Public-facing methods ---------
    def addUser(self, username: str, password: str, email: str = None,
                fullname: str = None, usertype: str = "human", tokenExpires: bool = True) -> "PublicUser":
        if username in self.accounts:
            raise HTTPException(status_code=400, detail="User already exists")

        if usertype not in ["bot", "admin", "human"]:
            raise HTTPException(status_code=400, detail="Invalid usertype")

        hashed_password = self.hashPassword(password)
        self.accounts[username] = {
            "username": username,
            "email": email,
            "fullname": fullname,
            "usertype": usertype,
            "disabled": False,
            "password": hashed_password,
            "tokenVersion": 1,
            "tokenExpires": tokenExpires
        }
        self.saveUsers()
        return PublicUser(**self.accounts[username])  # Return safe version

    def disableUser(self, username: str) -> "PublicUser":
        if username not in self.accounts:
            raise HTTPException(status_code=404, detail="User not found")

        user = self.accounts[username]
        user["disabled"] = True
        user["tokenVersion"] = (user.get("tokenVersion") or 0) + 1

        self.saveUsers()
        return PublicUser(**user)  # Return safe version

    def deleteUser(self, username: str) -> dict:
        """Delete a user from the accounts."""
        if username not in self.accounts:
            raise HTTPException(status_code=404, detail="User not found")

        del self.accounts[username]
        self.saveUsers()
        return {"detail": f"User '{username}' deleted"}

class User(BaseModel):
    username: str
    email: Union[str, None] = None
    fullname: Union[str, None] = None
    usertype: Union[str, None] = None
    disabled: Union[bool, None] = None
    password: str
    tokenVersion: Union[int, None] = None
    tokenExpires: bool = True

class PublicUser(BaseModel):
    username: str
    email: Union[str, None] = None
    fullname: Union[str, None] = None
    usertype: Union[str, None] = None
    disabled: Union[bool, None] = None
    tokenVersion: Union[int, None] = None
    tokenExpires: bool = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Union[str, None] = None,
    version: Union[int, None] = None

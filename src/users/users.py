import json
import os
from pathlib import Path
from typing import Dict, Mapping, Union
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
import jwt
#import passlib
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from fastapi import HTTPException, status

class Accounts:
    def __init__(self):

        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.accounts: Dict[str, Dict[str, object]] = {}

        self.userFile = Path(os.getenv('DATABOARD_USERFILE') or Path(__file__).with_name('users.json'))
        self.userFile.parent.mkdir(parents=True, exist_ok=True)
        if self.userFile.exists():
            with self.userFile.open('r', encoding='utf-8') as f:
                self.accounts = json.load(f)

    # --------- Internal-only methods ---------
    def saveUsers(self):
        """Persist current users to the JSON file."""
        with self.userFile.open("w", encoding="utf-8") as f:
            json.dump(self.accounts, f, indent=2)


    def getUser(self, username: str) -> Union["User", None]:
        """Return internal user (with password hash)."""
        user_dict = self.accounts.get(username)
        if isinstance(user_dict, Mapping):
            return User(**dict(user_dict))

    def authUser(self, username: str, password: str) -> Union["User", bool]:
        """Authenticate user using password hash."""
        user = self.getUser(username)
        if not user:
            return False
        if not self.pwd_context.verify(password, user.password):
           return False
        return user

    def _user_is_verified(self, user: "User") -> bool:
        return bool(getattr(user, "emailVerified", True))

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
        return int(os.getenv('DATABOARD_SECRET_EXPIRES', 60 * 24))

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
        if user.disabled or not self._user_is_verified(user):
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
        auth_user = self.authUser(form_data.username, form_data.password)
        if not isinstance(auth_user, User):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = auth_user
        if user.disabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )
        if not self._user_is_verified(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email address not verified",
            )

        access_token = self.createAccessToken(
            data={"sub": user.username, "version": user.tokenVersion},
            expires_delta= timedelta(minutes=int(self.getExpires())) if user.tokenExpires else None
        )
        return Token(access_token=access_token, token_type="bearer")

    def createVerificationToken(self, username: str, email: str, expires_delta: Union[timedelta, None] = None):
        """Create a short-lived JWT for email verification."""
        to_encode: Dict[str, object] = {
            "sub": username,
            "email": email,
            "purpose": "verify-email",
        }
        valid_for = expires_delta or timedelta(hours=24)
        expire = datetime.now(timezone.utc) + valid_for
        to_encode["exp"] = expire
        return jwt.encode(to_encode, self.getSecretKey(), algorithm=self.getAlgorithm())

    def verifyEmailToken(self, token: str) -> "PublicUser":
        """Validate an email verification token and activate the account."""
        credException = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

        try:
            payload = jwt.decode(token, self.getSecretKey(), algorithms=[self.getAlgorithm()])
        except InvalidTokenError:
            raise credException

        if payload.get("purpose") != "verify-email":
            raise credException

        username = payload.get("sub")
        email = payload.get("email")
        if not username or not email:
            raise credException

        user = self.getUser(username)
        if not isinstance(user, User):
            raise credException
        if user.email != email:
            raise credException

        if user.emailVerified:
            return PublicUser(**self.accounts[username])

        user_record = self.accounts[username]
        user_record["emailVerified"] = True
        user_record["disabled"] = False
        user_record["tokenVersion"] = (user_record.get("tokenVersion") or 0) + 1
        self.saveUsers()
        return PublicUser(**user_record)

    # --------- Public-facing methods ---------
    def addUser(self, username: str, password: str, email: str = None,
                fullname: str = None, usertype: str = "human", tokenExpires: bool = True,
                rateLimit: Dict[str, Dict[str, int]] = None,
                emailVerified: bool = True,
                disabled: bool = False) -> "PublicUser":
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
            "disabled": disabled,
            "password": hashed_password,
            "tokenVersion": 1,
            "tokenExpires": tokenExpires,
            "rateLimit": rateLimit or {},
            "emailVerified": emailVerified,
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
    emailVerified: bool = True
    password: str
    tokenVersion: Union[int, None] = None
    tokenExpires: bool = True
    rateLimit: Dict[str, Dict[str, int]] = Field(default_factory=dict)

class PublicUser(BaseModel):
    username: str
    email: Union[str, None] = None
    fullname: Union[str, None] = None
    usertype: Union[str, None] = None
    disabled: Union[bool, None] = None
    emailVerified: bool = True
    tokenVersion: Union[int, None] = None
    tokenExpires: bool = True
    rateLimit: Dict[str, Dict[str, int]] = Field(default_factory=dict)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Union[str, None] = None,
    version: Union[int, None] = None

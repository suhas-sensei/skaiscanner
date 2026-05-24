import graphene
from django.contrib.auth import login, logout

from .services import request_email_otp, verify_email_otp


class UserType(graphene.ObjectType):
    id = graphene.ID()
    email = graphene.String()
    username = graphene.String()


class RequestEmailOTP(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)

    ok = graphene.Boolean()
    expires_at = graphene.DateTime()

    @classmethod
    def mutate(cls, root, info, email):
        otp = request_email_otp(email)
        return RequestEmailOTP(ok=True, expires_at=otp.expires_at)


class VerifyEmailOTP(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        code = graphene.String(required=True)

    ok = graphene.Boolean()
    user = graphene.Field(UserType)

    @classmethod
    def mutate(cls, root, info, email, code):
        user = verify_email_otp(email, code)
        if user is None:
            return VerifyEmailOTP(ok=False, user=None)
        login(info.context, user)
        return VerifyEmailOTP(ok=True, user=user)


class SignOut(graphene.Mutation):
    ok = graphene.Boolean()

    @classmethod
    def mutate(cls, root, info):
        logout(info.context)
        return SignOut(ok=True)


class Query(graphene.ObjectType):
    viewer = graphene.Field(UserType)

    def resolve_viewer(self, info):
        user = info.context.user
        return user if user.is_authenticated else None


class Mutation(graphene.ObjectType):
    request_email_otp = RequestEmailOTP.Field()
    verify_email_otp = VerifyEmailOTP.Field()
    sign_out = SignOut.Field()

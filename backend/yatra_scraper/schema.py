import graphene

import accounts.schema
import flights.schema


class Query(accounts.schema.Query, flights.schema.Query, graphene.ObjectType):
    pass


class Mutation(accounts.schema.Mutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)

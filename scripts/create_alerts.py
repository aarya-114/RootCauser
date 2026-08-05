from signoz.client import SignozClient

client = SignozClient()

rules = client.get("/api/v1/rules")

print(rules)
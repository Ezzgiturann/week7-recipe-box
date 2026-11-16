# Integration check (merged main, uvicorn on :8001)
```
created Omelette id=3
created Crepes id=4
$ GET /recipes?tag=breakfast 
[{"id":1,"title":"Pancakes","ingredients":["flour","milk"],"tags":["breakfast"]},{"id":3,"title":"Omelette","ingredients":["2 eggs","Milk","salt"],"tags":["Breakfast"]},{"id":4,"title":"Crepes","ingredients":["flour","milk","2 eggs"],"tags":["dessert","breakfast"]}]  [HTTP 200]
# tag filter -> ids=1,3,4 -> shopping list:
$ GET /shopping-list?ids=1,3,4 
{"items":["flour","milk","2 eggs","salt"]}  [HTTP 200]
$ GET /recipes?tag=BREAKFAST&tag=dessert 
[{"id":1,"title":"Pancakes","ingredients":["flour","milk"],"tags":["breakfast"]},{"id":3,"title":"Omelette","ingredients":["2 eggs","Milk","salt"],"tags":["Breakfast"]},{"id":4,"title":"Crepes","ingredients":["flour","milk","2 eggs"],"tags":["dessert","breakfast"]}]  [HTTP 200]
$ GET /shopping-list?ids=3,99999 
{"detail":"unknown recipe ids: [99999]"}  [HTTP 404]
$ GET /shopping-list?ids=3,abc 
{"detail":"ids must be a comma-separated list of integers"}  [HTTP 422]
$ GET /recipes?tag= 
{"detail":"tag must not be empty"}  [HTTP 422]
```

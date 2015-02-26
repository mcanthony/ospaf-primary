import sys
sys.path.append("../../..")
import re
import threading
import socket
import base64
import json
import httplib
import urllib
import urllib2
import datetime
import pymongo
from pymongo import MongoClient
from GithubUser.DMLib.DMDatabase import DMDatabase
from GithubUser.DMLib.DMSharedUsers import DMSharedUsers
from GithubUser.DMLib.DMTask import DMTask

def add_commit (db, sha, full_name):
    res = db["commit_check_result"].find_one({"sha":sha})
    if res:
        repo_list = res["repos"]
        if full_name in repo_list:
            return
        else:
            repo_list.append(full_name)
            db["commit_check_result"].update({"_id": res["_id"]}, {"$set": {"repos": repo_list, "count": res["count"]+1}})
    else:
        db["commit_check_result"].insert({"sha": sha, "repos": [full_name], "count":1})

def get_certain_commits(full_name, param):
    url = "https://api.github.com/repos/"+full_name+"/commits"
    print url
    return DMSharedUsers().readURL(url, param)

def get_commits(db, full_name, date_list):
    for item in date_list:
        ret_val = get_certain_commits(full_name, item)
        if ret_val["error"] == 0:
            if len(ret_val["val"]) > 0:
                print "Get " + full_name
                for commit in ret_val["val"]:
                    add_commit (db, commit["sha"], full_name)

def get_date_list():
    date_list = []
    for year in range(2004, 2015):
        time_slot = {"since": str(year)+"-10-16T01:01:01Z", "until": str(year)+"-11-16T01:01:01Z"}
        date_list.append(time_slot)
    return date_list

def get_commit_repos_by_user(db, user):
    res =db["user_contributor_result2"].find_one({"login": user})
    if res:
        date_list = get_date_list()
        repo_list = res["repo_list"]
        for repo in repo_list:
           #if the repo is already added, no need to re-generate that 
           if db["commit_check_meta_result"].find_one({"full_name": repo["full_name"]}):
               continue
           get_commits(db, repo["full_name"], date_list)
           db["commit_check_meta_result"].insert({"full_name": repo["full_name"]})

def get_commit_repos_by_query(db, query):
    res =db["user_contributor_result2"].find(query)
    date_list = get_date_list()
    i = 0
    for item in res:
        i += 1
        print i
        repo_list = item["repo_list"]
        for repo in repo_list:
           #if the repo is already added, no need to re-generate that 
           if db["commit_check_meta_result"].find_one({"full_name": repo["full_name"]}):
               continue
           get_commits(db, repo["full_name"], date_list)
           db["commit_check_meta_result"].insert({"full_name": repo["full_name"]})
        

def main(type):
    timeout = 300
    socket.setdefaulttimeout(timeout)

    print "Account has " + str(DMSharedUsers().getRemaining()) + " API calls"

    db = DMDatabase().getDB()
    if db:
        if type == "user":
            user = "torvalds"
            get_commit_repos_by_user(db, user)
        elif type == "query":
            query = {"contributor_repos": {"$gte": 200}}
            get_commit_repos_by_query(db, query)

type = "query"
main(type)
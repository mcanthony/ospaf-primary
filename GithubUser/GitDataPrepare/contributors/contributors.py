import sys
sys.path.append("../../..")

import threading

import base64
import json
import urllib
import urllib2
import datetime
import pymongo
from pymongo import MongoClient
from GithubUser.DMLib.DMDatabase import DMDatabase
from GithubUser.DMLib.DMTask import DMTask
from GithubUser.DMLib.DMSharedUsers import DMSharedUsers

class GithubContributors:
    def __init__(self, task):
        self.task = task
        self.db = DMDatabase().getDB()

#https://developer.github.com/v3/repos
#GET /repos/:owner/:repo
#List contributors : /repos/:owner/:repo/contributors
    def append_contributors(self, full_name, page):
        url = "https://api.github.com/repos/"+full_name+"/contributors?page="+str(page);
        return DMSharedUsers().readURL(url)

    def get_slim(self, ret_val):
        slim_val = []
        for item in ret_val:
            slim_val.append({"login": item["login"], "id": item["id"], "type": item["type"],
                             "site_admin": item["site_admin"], "contributions": item["contributions"]})
        return slim_val

    def get_contributors(self, full_name):
        res = []
        i = 1
        timeout_time = 0
        while 1:
            ret_val = self.append_contributors(full_name, i)
            if ret_val["error"] == 1:
                timeout_time += 1
#NOTE: if we retry too many times..  the API is easily to reach the limitation
                if (timeout_time < 3):
                    print "timeout retry " + full_name + " " + str(i) + " " + str(timeout_time) + "times"
                    continue
                else:
                    return {"error": 1}
            timeout_time = 0
            slim_val = self.get_slim(ret_val["val"])
            res += slim_val
            if len(slim_val) < 30:
                    break
            i += 1

        return {"error": 0, "val": res}

    def get_repo_contributors(self, full_name, id):
        ret_val = self.get_contributors(full_name)
        if ret_val["error"] == 1:
#FIXME: dliang: since we have lots of error in current enviornment, or maybe github is slow in react to this call?, don't save it...
            return
            self.task.error({"full_name": full_name, "id": id, "message": "error in upload_contributors_contributors"})
        else:
            count = len(ret_val["val"])
#            print "insert " + full_name + "with " + str(count)
            self.db["contributors"].insert({"full_name": full_name, "id": id, "contributors": ret_val["val"], 
                                            "count": count, "update_date": datetime.datetime.utcnow()})
            self.db["repositories"].update({"full_name": full_name, "id": id}, {"$set": {"contributors_count": count}})

    def validateTask(self):
        info = self.task.getInfo()
        if info["start"] > info["end"]:
            print "Error in the task"
            return 0
        return 1

#return the solved errors
    def error_check (self):
        info = self.task.getInfo()
        print info
        if info["status"] == "init":
            return 0

        count = 0
        if info.has_key("error"):
#FIXME: this is just lazy way, error_count < 10 means the repo is gone, the error is not caused by our program or network..
            if info["error_count"] < 10:
                return 0
            update_error = []
            list = info["error"]
            for item in list:
                full_name = item["full_name"]
                id = item["id"]
                if self.db["contributors"].find_one({"id": id}):
                    count += 1
                    continue
                print "solve error for " + full_name
                ret = self.get_contributors(full_name)
# error
                if ret == 1:
                    update_error.append({"full_name": full_name, "id": id, "message": "error even in double upload_user_event"})
                else:
                    count += 1
            error_len = len(update_error)
            self.task.update({"error": update_error, "error_count": error_len})
        return count

    def runTask(self):
        info = self.task.getInfo()
        if info["action_type"] == "loop":
            self.runLoopTask()
        elif info["action_type"] == "update":
            self.runUpdateTask()

    def runUpdateTask(self):
        print "Not implemented"
        return
        if self.validateTask() == 0:
            return
        if self.task.updateStatus("running") != 0:
            return

        info = self.task.getInfo()
        start_id = info["start"]
        if info.has_key("current"):
            start_id = info["current"]
            print "Find unfinished task, continue to work at " + str(start_id)

        last_id = start_id

    def dupCheck(self, dup_list):
        for item in dup_list:
            res = self.db["contributors"].find({"id": item["id"]})
            dup_con = []
            last_id = 0
#TODO, pop is ok..
            for con_item in res:
                if last_id == 0:
                    last_id = 1
                else:
                    dup_con.append(con_item["_id"])
            for con_item in dup_con:
                print "\n------------------We find dup one!\n\n\n"
                self.db["contributors"].remove({"_id": con_item})

    def runLoopTask(self):
        if self.validateTask() == 0:
            return
        if self.task.updateStatus("running") != 0:
            return

        info = self.task.getInfo()
        start_id = info["start"]
        end_id = info["end"]
#Dliang marks this to do fix work...
        if info.has_key("current"):
            start_id = info["current"]
            print "Find unfinished task, continue to work at " + str(start_id)

        query = {"id": {"$gte": start_id, "$lt": end_id}}

        res = self.db["repositories"].find(query).sort("id", pymongo.ASCENDING)
        res_list = []
#        dup_check = []
        for item in res:
            if item.has_key("contributors_count"):
#                print item["full_name"] + " already exist"
#                dup_check.append({"full_name": item["full_name"], "id": item["id"]})
                continue
            else:
                res_list.append({"full_name": item["full_name"], "id": item["id"]})

#        self.dupCheck(dup_check)

        res_len = len(res_list)
        i = 0
        percent_gap = res_len/100

        for item in res_list:
            i += 1
#            saved_res = self.db["contributors"].find_one({"id": item["id"]})
#            if saved_res:
#                print "How could it possible!\n\n"
#                continue
            self.get_repo_contributors(item["full_name"], item["id"])
#Dliang fix memo
            print "Fix " + item["full_name"]
            if percent_gap == 0:
                percent = 1.0 * i / res_len
                self.task.update({"current": item["id"], "percent": percent, "update_date": datetime.datetime.utcnow()})
#save every 100 calculate 
            elif i%percent_gap == 0:
                percent = 1.0 * i / res_len
                self.task.update({"current": item["id"], "percent": percent, "update_date": datetime.datetime.utcnow()})

        self.task.update({"status": "finish", "current": end_id, "percent": 1.0, "update_date": datetime.datetime.utcnow()})
        print "Task finish, exiting the thread"

# very important, the entry function
def init_contributors_task():
# 1000 is system defined, maybe add to DMTask? or config file?
    gap = 1000
    start = 0
# end id is now set to 29000000
    end = 29000
    db = DMDatabase().getDB()
    for i in range (start, end):
        task = DMTask()
        val = {"name": "get_contributors", "action_type": "loop", "start": i * gap, "end": (i+1)*gap}
        task.init("github", val)

def resolve_contributors_loop_errors():
    print "resolve contributors errors"
    gap = 1000
    start = 0
    end = 29000
    count = 0
    for i in range (start, end):
        task = DMTask()
        val = {"name": "get_contributors", "action_type": "loop", "start": i * gap, "end": (i+1)*gap}
        task.init("github", val)
        r = GithubContributors(task)
        res = r.error_check()
        count += res
    print str(count) + " errors solved"


# unlike init_contributors_task, this is used to get new contributorss
def updated_contributors_task():
    last_id  = get_last_saved_id()
    task = DMTask()
    val = {"name": "get_contributors", "action_type": "update", "start": last_id, "end": 0}
    task.init("github", val)

#init_contributors_task()
#resolve_contributors_loop_errors()

def resolve_dup(db, start_id, end_id):
    query = {"id": {"$gte": start_id, "$lt": end_id}}
    res = db["contributors"].find(query).sort("id", pymongo.ASCENDING)
    last_id = 0
    count = 0
    for item in res:
        if last_id == 0:
            last_id = item["id"]
        else:
            if last_id == item["id"]:
                count += 1
                print "remove " + item["full_name"]
                db["contributors"].remove({"_id": item["_id"]})
        last_id = item["id"]
    return count

def resolve_contributors_dups():
    gap = 1000
    start = 0
    end = 29000
    count = 0
    db = DMDatabase().getDB()
    for i in range (start, end):
        i_count = resolve_dup(db, i*gap, (i+1)*gap)
        count += 0
        print str(i_count) + "  dups in " + str(start)
    print "total + " + str(count) + " dups"

#resolve_contributors_dups()

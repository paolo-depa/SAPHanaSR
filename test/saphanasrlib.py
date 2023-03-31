"""
 saphanasrtest.py
 Author:       Fabian Herschel, Mar 2023
 License:      GNU General Public License (GPL)
 Copyright:    (c) 2023 SUSE LLC
"""

import time
import subprocess
import re
import sys, json
import argparse
import random

""" for ssh remote calls this module uses paramiko """
from paramiko import SSHClient

class saphanasrtest:
    """
    class to check SAP HANA cluster during tests
    """
    version = "0.1.20230324.1239"

    def message(self, msg):
        """
        message with formatted timestamp
        """
        """ TODO: specify, if message should be written to stdout, stderr and/or log file """
        dateTime = time.strftime("%Y-%m-%d %H:%M:%S")
        if self.rID:
            rID = " [{}]".format(self.rID)
        else:
            rID = ""
        msgArr = msg.split(" ")
        print("{}{} {:<9s} {}".format(dateTime, rID, msgArr[0], " ".join(msgArr[1:])))
        try:
            self.messageFH(msg, self.logFileHandle)
        except:
            print("{0} {1:<9s} {2}".format(dateTime, "ERROR:", "Could not write log logFile"))

    def messageFH(self, msg, fileHandle):
        dateTime = time.strftime("%Y-%m-%d %H:%M:%S")
        if self.rID:
            rID = " [{}]".format(self.rID)
        else:
            rID = ""
        msgArr = msg.split(" ")
        if fileHandle:
            fileHandle.write("{}{} {:<9s} {}\n".format(dateTime, rID, msgArr[0], " ".join(msgArr[1:])))

    def __init__(self, *args):
        """
        constructor
        """
        self.logFileHandle = None
        self.rID = None
        self.message("INIT: {}".format(self.version))
        self.SR = {}
        self.testData = {}
        self.testFile = "-"
        self.defaultChecksFile = None
        self.propertiesFile = "properties.json"
        self.logFile = ""
        self.repeat = 1
        self.dumpFailures = False
        self.topolo = { 'pSite': None, 'sSite': None, 'pHost': None, 'sHost': None }
        self.remoteNode = None
        parser = argparse.ArgumentParser()
        parser.add_argument("--testFile", help="specify the test file")
        parser.add_argument("--defaultChecksFile", help="specify the default checks file")
        parser.add_argument("--propertiesFile", help="specify the properties file")
        parser.add_argument("--remoteNode", help="cluster node to use for ssh connection")
        parser.add_argument("--simulate", help="only simulate, dont call actions", action="store_true")
        parser.add_argument("--repeat", help="how often to repeat the test")
        parser.add_argument("--dumpFailures", help="print failed checks per loop", action="store_true")
        parser.add_argument("--logFile", help="log file to write the messages")
        args = parser.parse_args()
        if args.testFile:
            self.message("PARAM: testFile: {}".format(args.testFile))
            self.testFile = args.testFile
        if args.defaultChecksFile:
            self.message("PARAM: defaultChecksFile: {}".format(args.defaultChecksFile))
            self.defaultChecksFile = args.defaultChecksFile
        if args.propertiesFile:
            self.message("PARAM: propertiesFile: {}".format(args.propertiesFile))
            self.propertiesFile = args.propertiesFile
        if args.remoteNode:
            self.message("PARAM: remoteNode: {}".format(args.remoteNode))
            self.remoteNode = args.remoteNode
        if args.repeat:
            self.message("PARAM: repeat: {}".format(args.repeat))
            self.repeat = int(args.repeat)
        if args.dumpFailures:
            self.message("PARAM: repeat: {}".format(args.dumpFailures))
            self.dumpFailures = args.dumpFailures
        if args.logFile:
            self.message("PARAM: logFile: {}".format(args.logFile))
            self.logFile = args.logFile
            self.logFileHandle = open(self.logFile, 'a')
        random.seed()

    def insertToArea(self, area, object):
        """ insert an object dictionary to an area dictionary """
        lSR = self.SR.copy()
        if area in lSR:
            lDic = lSR[area].copy()
            lDic.update(object)
            lSR[area].update(lDic)
        else:
            lDic = { area: object }
            lSR.update(lDic)
        self.SR = lSR.copy()

    def getObject(self, area, objectName):
        """ get an object dictionary inside the area dictionary """
        lSR = self.SR.copy()
        if area in lSR:
            if objectName in lSR[area]:
                return lSR[area][objectName]
            else:
                return None
        else:
            return None

    def createObject(self, objectName, key, val):
        """ create a key: value dictionary for object objectName """
        lObj = { objectName: { key: val } }
        return lObj

    def insertToObject(self, object, key, value):
        """ insert a key-value pair into the object dictionary """
        lObj = object
        lDic = { key: value }
        lObj.update(lDic)
        return lObj

    def readSAPHanaSR(self):
        """ method to read SAPHanaSR-showAttr cluster attributes and create a nested dictionary structure representing the data """
        #cmd = [ './helpSAPHanaSR-showAttr', '--format=script'  ]
        cmd = "SAPHanaSR-showAttr --format=script"
        self.SR={}
        resultSR = self.doSSH(self.remoteNode, "root", cmd)
        for line in resultSR[0].splitlines():
            """ match and split: <area>/<object>/<key-value> """
            mo = re.search("(.*)/(.*)/(.*)", line)
            if mo:
                area = mo.group(1)
                objectName = mo.group(2)
                kV = mo.group(3)
                """ match and split <key>="<value>" """
                mo = re.search("(.*)=\"(.*)\"", kV)
                key = mo.group(1)
                val = mo.group(2)
                lObj=self.getObject(area, objectName)
                if lObj:
                    self.insertToObject(lObj,key,val)
                else:
                    lObj = self.createObject(objectName, key, val)
                    self.insertToArea(area, lObj)
        return 0

    def searchInAreaForObjectByKeyValue(self, areaName, key, value):
        """ method to search in SR for an ObjectName filtered by 'area' and key=value """
        objectName = None
        lSR = self.SR
        if areaName in lSR:
            lArea = lSR[areaName]
            for k in lArea.keys():
                lObj = lArea[k]
                if key in lObj:
                    if lObj[key] == value:
                        objectName = k
                        """ currently we only return the first match """
                        break
        return objectName

    def prettyPrint(self, dictionary,level):
        """ debug method for nested dictionary """
        print("{")
        count = 0
        for k in dictionary.keys():
            if count > 0:
                print(",")
            if isinstance(dictionary[k],dict):
                print("'{}': ".format(k))
                self.prettyPrint(dictionary[k], level+1)
            else:
                print("'{}': '{}'".format(k,dictionary[k]))
            count = count + 1
        print("}")

    def readTestFile(self):
        """ read Test Description, optionally defaultchecks and properties """
        if self.propertiesFile:
            f = open(self.propertiesFile)
            self.testData.update(json.load(f))
            f.close()
        if self.defaultChecksFile:
            f = open(self.defaultChecksFile)
            self.testData.update(json.load(f))
            f.close()
        if self.testFile == "-":
            self.testData.update(json.load(sys.stdin))
        else:
            f = open(self.testFile)
            self.testData.update(json.load(f))
            f.close()
        self.messageFH("DEBUG: testData: {}".format(str(self.testData)),self.logFileHandle)

    def runChecks(self, checks, areaName, objectName ):
        """ run all checks for area and object """
        lSR = self.SR
        checkResult = -1
        failedChecks = ""
        for c in checks:
            """ match <key>=<regExp> """
            mo = re.search("(.*)(=)(.*)",c)
            cKey = mo.group(1)
            cComp = mo.group(2)
            cRegExp = mo.group(3)
            found = 0
            if areaName in lSR:
                lArea = lSR[areaName]
                if objectName in lArea:
                    lObj = lArea[objectName]
                    if cKey in lObj:
                        lVal = lObj[cKey]
                        found = 1
                        if re.search(cRegExp, lVal):
                            if checkResult <0:
                                checkResult = 0
                        else:
                            if failedChecks == "":
                                failedChecks = "{}={}: {}={} !~ {}".format(areaName,objectName,cKey,lVal,cRegExp)
                            else:
                                failedChecks += "; {}={} !~ {}".format(cKey,lVal,cRegExp)
                            if checkResult <1:
                                checkResult = 1
            if (found == 0) and (checkResult < 2 ):
                checkResult = 2
        if self.dumpFailures and failedChecks != "":
            self.messageFH("FAILED: {}".format(failedChecks), self.logFileHandle)
        return checkResult

    def processTopologyObject(self, step, topologyObjectName, areaName):
        rcChecks = -1
        if topologyObjectName in step:
            checks = step[topologyObjectName]
            if type(checks) is str: 
                checkPtr = checks
                self.messageFH("DEBUG: checkPtr {}".format(checkPtr), self.logFileHandle)
                checks = self.testData["checkPtr"][checkPtr]
                #for c in checks:
                #    self.message("DEBUG: checkPtr {} check {}".format(checkPtr,c))
            topolo = self.topolo
            if topologyObjectName in topolo:
                objectName = topolo[topologyObjectName]
                rcChecks = self.runChecks(checks, areaName, objectName)
        return(rcChecks)

    def processStep(self, step):
        """ process a single step including optional loops """
        stepID = step['step']
        stepName = step['name']
        stepNext = step['next']
        if 'loop' in step:
            maxLoops = step['loop']
        else:
            maxLoops = 1
        if 'wait' in step:
            wait = step['wait']
        else:
            wait = 2
        loops = 0
        if 'post' in step:
            stepAction = step['post']
        else:
            stepAction = ""
        self.message("PROC: stepID={} stepName='{}' stepNext={} stepAction='{}'".format(stepID, stepName, stepNext, stepAction))
        while loops < maxLoops:
            loops = loops + 1
            if self.dumpFailures == False:
                print(".", end='', flush=True)
            processResult = -1
            self.readSAPHanaSR()
            processResult = max ( self.processTopologyObject(step, 'pSite', 'Sites'),
                                  self.processTopologyObject(step, 'sSite', 'Sites'),
                                  self.processTopologyObject(step, 'pHost', 'Hosts'),
                                  self.processTopologyObject(step, 'sHost', 'Hosts'))
            if processResult == 0:
                break
            else:
                time.sleep(wait)
        if self.dumpFailures == False:
            print("")
        self.message("STATUS: step {} checked in {} loop(s)".format(stepID, loops))
        if processResult == 0:
            aRc = self.action(stepAction)
        return processResult

    def processSteps(self):
        """ process a seria of steps till next-step is "END" or there is no next-step """
        testStart = self.testData['start']
        step=self.getStep(testStart)
        stepStep = step['step']
        rc = 0
        """ onfail for first step is 'break' """
        onfail = 'break' 
        while stepStep != "END":
            stepNext = step['next']
            processResult = self.processStep(step)
            if processResult == 0:
                self.message("STATUS: Test step {} passed successfully".format(stepStep))
            else:
                rc = 1
                self.message("STATUS: Test step {} FAILED successfully ;-)".format(stepStep))
                """ TODO: add onfail handling (cuurently only brak for furst step and continue for others) """
                if onfail == 'break':
                    break
            step=self.getStep(stepNext)
            if step:
                stepStep = step['step']
            else:
                """ check, why we run into this code path """
                break
            """ onfail for all next steps is 'continue' to run also the recovery steps """
            onfail = 'continue'
        return(rc)

    def processTest(self):
        """ process the entire test defined in testData """
        testID = self.testData['test']
        testName = self.testData['name']
        testStart = self.testData['start']
        testSID = self.testData['sid']
        testResource = self.testData['mstResource']
        self.message("PROC: testID={} testName={} testStart={} testSID={}".format(testID, testName, testStart, testSID, testResource))
        rc = self.processSteps()
        return(rc)

    def getStep(self, stepName):
        """ query for a given step with stepName in testData """
        step = None
        for s in self.testData['steps']:
            if s['step'] == stepName:
                step = s
                break
        return step

    def action(self, actionName):
        """ perform a given action """
        remote = self.remoteNode
        cmd = ""
        aRc = 1
        # resource = "ms_SAPHanaCon_HA1_HDB00"
        testSID = self.testData['sid']
        resource = self.testData['mstResource']
        actionArr = actionName.split(" ")
        actionNameShort = actionArr[0]
        if actionName == "":
            aRc = 0
        elif actionName == "ksi":
            remote = self.topolo['sHost']
            cmd = "su - {}adm HDB kill-9".format(testSID.lower())
        elif actionName == "kpi":
            remote = self.topolo['pHost']
            cmd = "su - {}adm HDB kill-9".format(testSID.lower())
        elif actionName == "kpx":
            remote = self.topolo['pHost']
            cmd = "pkill -f -u {}adm --signal 11 hdbindexserver".format(testSID.lower())
        elif actionName == "ksx":
            remote = self.topolo['sHost']
            cmd = "pkill -f -u {}adm --signal 11 hdbindexserver".format(testSID.lower())
        elif actionName == "bmt":
            remote = self.topolo['sHost']
            cmd = "su - {}adm -c 'hdbnsutil -sr_takeover'".format(testSID.lower())
        elif actionName == "ssn":
            remote = self.remoteNode
            cmd = "crm node standby {}".format(self.topolo['sHost'])
        elif actionName == "osn":
            remote = self.remoteNode
            cmd = "crm node online {}".format(self.topolo['sHost'])
        elif actionName == "spn":
            remote = self.remoteNode
            cmd = "crm node standby {}".format(self.topolo['pHost'])
        elif actionName == "opn":
            remote = self.remoteNode
            cmd = "crm node online {}".format(self.topolo['pHost'])
        elif actionName == "cleanup":
            """ TODO: get resource name from testData """
            remote = self.remoteNode
            cmd = "crm resource cleanup {}".format(resource)
        elif actionNameShort == "sleep":
            remote = self.remoteNode
            if len(actionArr) == 2:
                actionParameter = actionArr[1]
            else:
                actionParameter = "60"
            cmd = "sleep {}".format(actionParameter)
        elif actionNameShort == "shell":
            remote = 'localhost'
            actionParameter = " ".join(actionArr[1:])
            cmd = "bash {}".format(actionParameter)
        if cmd != "":
            self.message("ACTION: {} at {}: {}".format(actionName, remote, cmd))
            aResult = self.doSSH(remote, "root", cmd)
            aRc = aResult[2]
            self.message("ACTION: {} at {}: {} rc={}".format(actionName, remote, cmd, aRc))
        return(aRc)

    def doSSH(self, remoteHost, user, cmd):
        """
        ssh remote cmd exectution
        returns a tuple ( stdout-string, stderr, string, rc )
        """
        if remoteHost:
            sshCl = SSHClient()
            sshCl.load_system_host_keys()
            sshCl.connect(remoteHost, username=user)
            (cmdStdin, cmdStdout, cmdStderr) = sshCl.exec_command(cmd)
            resultStdout = cmdStdout.read().decode("utf8")
            resultStderr = cmdStderr.read().decode("utf8")
            resultRc = cmdStdout.channel.recv_exit_status()
            checkResult = (resultStdout, resultStderr, resultRc)
            sshCl.close()
        else:
            checkResult=("", "", 20000)
        return(checkResult)

if __name__ == "__main__":
    test01 = saphanasrtest()
    test01.count = 1
    while test01.count <= test01.repeat:
        test01.rID = random.randrange(10000,99999,1)
        test01.readSAPHanaSR()
        test01.topolo.update({'pSite': test01.searchInAreaForObjectByKeyValue('Sites', 'srr', 'P')})
        test01.topolo.update({'sSite': test01.searchInAreaForObjectByKeyValue('Sites', 'srr', 'S')})
        test01.topolo.update({'pHost': test01.searchInAreaForObjectByKeyValue('Hosts', 'site', test01.topolo['pSite'])})
        test01.topolo.update({'sHost': test01.searchInAreaForObjectByKeyValue('Hosts', 'site', test01.topolo['sSite'])})
        test01.message("TOPO: pSite={} sSite={} pHost={} sHost={}".format(test01.topolo['pSite'], test01.topolo['sSite'], test01.topolo['pHost'], test01.topolo['sHost']))
        test01.readTestFile()
        testID = test01.testData['test']
        if test01.repeat != 1:
            test01.message("TEST: {} testNr={} ######".format(testID, test01.count))
        rc = test01.processTest()
        if rc == 0:
            test01.message("TEST: {} testNr={} PASSED successfully :) ######".format(testID, test01.count)) 
        else:
            test01.message("TEST: {} testNr={} FAILED successfully ;) ######".format(testID, test01.count)) 
        test01.count += 1
    if  test01.logFileHandle:
        test01.logFileHandle.close()
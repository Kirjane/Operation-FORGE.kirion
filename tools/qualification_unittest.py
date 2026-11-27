"""Execute unittest and emit case identities from result callbacks, not discovery counts."""
import argparse
import json
import sys
import unittest


class CaseResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.rows=[]

    def record(self,test,status):
        self.rows.append({"id":test.id(),"status":status})

    def addSuccess(self,test):
        super().addSuccess(test)
        self.record(test,"PASS")

    def addFailure(self,test,err):
        super().addFailure(test,err)
        self.record(test,"FAIL")

    def addError(self,test,err):
        super().addError(test,err)
        self.record(test,"ERROR")

    def addSkip(self,test,reason):
        super().addSkip(test,reason)
        self.record(test,"SKIP")

    def addExpectedFailure(self,test,err):
        super().addExpectedFailure(test,err)
        self.record(test,"XFAIL")

    def addUnexpectedSuccess(self,test):
        super().addUnexpectedSuccess(test)
        self.record(test,"XPASS")

    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err is not None:
            self.record(subtest,"SUBTEST_FAILURE")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("target")
    p.add_argument("-s",default=".")
    p.add_argument("-p",default="test*.py")
    p.add_argument("-v",action="store_true")
    args=p.parse_args()
    loader=unittest.TestLoader()
    suite=(loader.discover(args.s,pattern=args.p) if args.target=="discover"
           else loader.loadTestsFromName(args.target))
    result=unittest.TextTestRunner(verbosity=2,resultclass=CaseResult).run(suite)
    print("FORGE_CASE_RESULTS "+json.dumps(result.rows,sort_keys=True))
    return 0 if result.wasSuccessful() and result.rows and all(r["status"]=="PASS" for r in result.rows) else 1


if __name__=="__main__":
    sys.exit(main())

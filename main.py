#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO's list:
#   - Add <select/> element support
#   - Improve the way it looks for bad answers (current sometimes fails)
#   - Persist answers to a file

import logging
import re
import mechanize
import lxml.html as lxhtml
import time
from os.path import join, realpath
from datetime import timedelta

USER = "7162@utcv.edu.mx"
PASSWORD = "PASSPORT"

URLS = [
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=11270",
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=11271",
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=11299",
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=11300",
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=11803",
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=11804",
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=1868",
    "https://b-learning.utcv.edu.mx/mod/quiz/view.php?id=1869"
]

class ActivitySolver:
    LOGIN_URL = "https://b-learning.utcv.edu.mx/login/index.php"
    FINISH_URL = "https://b-learning.utcv.edu.mx/mod/quiz/processattempt.php"

    def __init__(self, user, password):
        self.user = user
        self.password = password
        self.reset_values()

        self.setup()

    def setup(self):
        self.check_ssl()

        logger = logging.getLogger()
        formatter = logging.Formatter('%(message)s')

        fileHandler = logging.FileHandler('info.log', mode='w')
        fileHandler.setFormatter(formatter)

        streamHandler = logging.StreamHandler()
        streamHandler.setFormatter(formatter)

        logger.setLevel(logging.INFO)
        logger.addHandler(fileHandler)
        logger.addHandler(streamHandler)

    def check_ssl(self):
        # Invalid SSL CERTIFICATE Fix
        import ssl
        if hasattr(ssl, '_create_unverified_context'):
            ssl._create_default_https_context = ssl._create_unverified_context
        
        # If above solution is not working comment it and uncomment this:
        # from functools import wraps
        # def sslwrap(func):
        #     @wraps(func)
        #     def bar(*args, **kw):
        #         kw['ssl_version'] = ssl.PROTOCOL_TLSv1
        #         return func(*args, **kw)
        #     return bar

        # ssl.wrap_socket = sslwrap(ssl.wrap_socket)

    def reset_values(self):
        self.correct_answers = {}
        self.incorrect_answers = {}
        self.attempt_number = 1
        self.all_correct = False

    def solve(self):
        self.br = mechanize.Browser()
        # Fix: HTTP Error 403: request disallowed by robots.txt
        self.br.set_handle_robots(False)
        self.signin()
        
        for url in URLS:
            self.url = url

            # BUG: finishes before all correct
            #while not self.all_correct and self.attempt_number <= 4:
            while self.attempt_number <= 4:
                self.start_attempt()
                self.fill_questions()
                self.finish_attempt()
                self.check_answers()

            self.save_summary_to_file()
            self.reset_values()

    def start_attempt(self):
        self.question_count = 0
        
        br = self.br
        br.open(self.url)

        logging.info("\nStarting attempt #{0} for {1}".format(self.attempt_number, br.title()))

        br.select_form(nr=1)
        br.submit()

    def finish_attempt(self):
        logging.info("Finishing attempt #{0}\n".format(self.attempt_number))

        br = self.br
        br.select_form(predicate=lambda f: f.action == self.FINISH_URL)
        br.submit()

        self.attempt_number += 1

    def valid_filename(self, filename):
        return "".join([l if l.isalnum() else "_" for l in filename])

    def save_summary_to_file(self):
        br = self.br
        html = br.response().read()

        br.open(self.url)
        title = self.valid_filename(br.title())
        filename = join('actividades', title + '.html')
        filepath = realpath(filename)
        
        logging.info("Saving answers to: " + filepath)

        with open(filepath, 'w') as f: 
            f.write(html)

    def signin(self):
        logging.info("Starting session with user: " + self.user.upper())

        br = self.br
        br.open(self.LOGIN_URL)
        
        for form in br.forms():
            if form.attrs.get('id') == 'login1':
                br.form = form
                break

        br["username"] = self.user
        br["password"] = self.password
        br.submit()

    def get_inputs_for(self, classname):
        html = self.br.response().read()
        doc = lxhtml.document_fromstring(html)
        expr = "//{ans_container}/{ans_opt}/{input}".format(
                ans_container="*[contains(@class, 'answer')]",
                ans_opt="*[contains(@class, ' {0}')]".format(classname),
                input="input[@type='radio']")
        return doc.xpath(expr)

    def save_answers_to(self, inputs, dictionary, append=False):
        for i in inputs:
            q_id = self.get_question_number(i.get("name"))
            
            # Since we have the input radio, we get the label next to it
            # And remove the letter preceding the answer since the letter
            # changes each attempt
            answer = i.getnext().xpath('text()')
            
            for i, ans in enumerate(answer):
                # Remove letter (example: 'a.') from the first line of the answer
                if i == 0:
                    ans = ans[2:]

                if isinstance(answer, str):
                    ans = ans.decode('utf-8')

                answer[i] = ans

            if len(answer) == 1:
                answer = answer[0]
            
            if append:
                ans_lst = dictionary.get(q_id, [])
                ans_lst.append(answer)
                dictionary[q_id] = ans_lst
            else:
                dictionary[q_id] = answer
                if isinstance(answer, list): answer = unicode(answer)
                logging.info("Saving answer ({0}: {1})".format(q_id, answer.encode('utf-8')))

    def check_answers(self):
        correct_inputs = self.get_inputs_for('correct')
        incorrect_inputs = self.get_inputs_for('incorrect')
        self.save_answers_to(correct_inputs, self.correct_answers)
        self.save_answers_to(incorrect_inputs, self.incorrect_answers, append=True)

        logging.info(self.correct_answers)
        logging.info(self.incorrect_answers)

        self.all_correct = len(self.correct_answers.keys()) == self.question_count

    def safe_string(self, string):
        # concat('str1', "'", 'str2')
        if "'" in string or '"' in string:
            return u"concat('{0}')".format(string.replace("'", "',\"'\",'"))
        return u"'{0}'".format(string)

    def _correct_answer(self, wrong_ans_list, label_text):
        for textlist in wrong_ans_list:
            if set(textlist) == set(label_text): return False
        return True

    def _get_with_textlist(self, labels, textlist, match_textlist):
        for label in labels:
            label_text = label.xpath('text()')

            # Remove letter (example: 'a.') from the first line of the answer
            label_text[0] = label_text[0][2:]

            if isinstance(textlist[0], list):
                if not self._correct_answer(textlist, label_text): continue
            else:
                match = set(textlist) == set(label_text)
                if match != match_textlist:
                    continue

            return label.getprevious().get("value")

    def get_value_with_expr(self, expr, textlist=None, match_textlist=True):
        html = self.br.response().read().decode('utf-8')
        doc = lxhtml.document_fromstring(html)

        logging.info("Getting with expr: {0}".format(expr.encode('utf-8')))

        if textlist is None:
            try:
                label = doc.xpath(expr)[0]
                # Get the value from the input radio right behind this label
                return label.getprevious().get("value")
            except:
                import ipdb; ipdb.set_trace()
        else:
            labels = doc.xpath(expr)
            return self._get_with_textlist(labels, textlist, match_textlist)

    def get_value_with_ans_not_like(self, answers, question_name):
        expr = u"//label[contains(@for, '{0}'){1}]"
        expr_complement = u""
        letters = ['a', 'b', 'c', 'd']
        textlist_array = None
        match_textlist = False

        for ans in answers:
            if isinstance(ans, list):
                try:
                    textlist_array.append(ans)
                except:
                    textlist_array = [ans]
            else:
                for letter in letters:
                    expr_complement += u" and text()!=concat('{0}.',{1})".format(
                            letter,
                            self.safe_string(ans))
        
        expression = expr.format(question_name, expr_complement)        
        return self.get_value_with_expr(expression, textlist=textlist_array, 
                match_textlist=match_textlist)

    def get_value_for_text(self, text, question_name):
        expr = u"//label[contains(@for, '{0}'){1}]"
        expr_complement = u""

        # ARREGLAR PARA QUE BUSQUE LA CADENA EXACTA (CON LETRAS)
        # DADO QUE SI LA RESPUESTA ES 'lower' Y EXISTE OTRA RESPUESTA QUE SEA
        # 'lowercase' LA TOMARÁ COMO CORRECTA

        if isinstance(text, list):
            expression = expr.format(question_name, '')
            return self.get_value_with_expr(expression, textlist=text)
        else:
            safe_text = self.safe_string(text)
            expr_complement = u" and contains(text(), {0})".format(safe_text)
        
        expression = expr.format(question_name, expr_complement)
        return self.get_value_with_expr(expression)

    def get_question_number(self, question_name):
        return re.search(".+:(\d+)", question_name).group(1)

    def get_best_answer(self, question_name):
        q_id = self.get_question_number(question_name)
        ans_txt = self.correct_answers.get(q_id)

        answer = str(self.attempt_number -1)
        if ans_txt is not None:
            answer = self.get_value_for_text(ans_txt, question_name)
        else:
            wrong_ans = self.incorrect_answers.get(q_id)
            if wrong_ans is not None:
                answer = self.get_value_with_ans_not_like(wrong_ans, question_name)

        return answer

    def fill_questions(self):
        br = self.br
        questions = True
        
        while questions:
            br.select_form(predicate=lambda f: f.action == self.FINISH_URL)
            questions = [c.name for c in br.form.controls if c.name and "answer" in c.name]

            if questions:
                for q in questions:
                    self.question_count += 1
                    answer = self.get_best_answer(q)
                    br[q] = [answer]

                    logging.info("Getting answer {0} for question {1}".format(answer, q))
                    logging.info("Filling # {0} question: {1} with answer: {2}\n".format(
                            self.question_count, q, answer))

                br.submit()


def main():
    print "Task started for {0}".format(USER)
    start_time = time.time()

    solver = ActivitySolver(USER, PASSWORD)
    solver.solve()

    final_time = time.time()
    total_time = timedelta(seconds=final_time-start_time)
    print "Task finished. Elapsed time: {0}".format(total_time)

if __name__ == '__main__':
    main()

#!/usr/bin/python

#Building Titles from Named Entity Recognition (NER)
#This script reads the NER json file and generates a title for every segment
#It also categorizes locations, topics, and reporters.

import os
import json
import re
from openai import OpenAI
import copy as cp
import datetime
import time
from shutil import copy


client = OpenAI()

def netFinder(path):
    filename = path
    if "/" in path:
        # split the path into a list of pieces based on slash, then grab the last piece
        pieces = path.split('/')
        filename = pieces[len(pieces)-1]
    network = filename[8:11]
    network = network.upper()
    return network

def convert_time(time,rate):
    try:
        messyTime = float(time) / rate
        messyTime = round(messyTime)
        cleanTime = str(datetime.timedelta(seconds=messyTime))
    except:
        print("ERROR converting Time")
        cleanTime = "ERROR"
    return cleanTime

def addCSTStart(cstStart,duration_str):
    # Parse the duration string
    duration_parts = duration_str.split(":")
    hours, minutes, seconds = map(int, duration_parts)
    duration = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)

    newTime = cstStart + duration

    netTimeString = datetime.datetime.strftime(newTime,'%H:%M:%S')
    return netTimeString


class ai:
    def make_summary(stream):
        prompt = f"""
            Write a summary for the text delimited by triple backticks \
            the summary should be no longer than 400 characters, \
            include relevant people, places and organizations. \
            use the corresponding IPTC media topic in the summary.\
            ```{stream}```
            """
        summary = ""
        summary = ai.get_completion(prompt)
        summary = summary.replace("(","[")
        summary = summary.replace(")","]")
        return summary
    
    def get_commercial_product(text):
        product = ""
        pattern = r"\[(.*?)\]"
        match = re.search(pattern, text)
        if match:
            product = "Commercial: " + match.group(1)  # Return the text within the brackets
        else:
            prompt = f"""
                Given the script of this television commercial, \
                delimited by triple backticks, what is the service or product? \
                output example: "Prevagen"
                do not tell me what the product does.
                ```{text}```
            """
            product = ai.get_completion(prompt)
            product = product.replace("The advertised product is ","")
            if len(product) > 25:
                product = "Commercial"
            else:
                product = "Commercial: " + product
        return product

    def get_story_title(text):
        title = ""
        text = text[:1000]
        prompt = f"""
            Given the news story, \
            delimited by triple backticks, create a 3 to 5 word headline \
            ```{text}```
        """
        title = ai.get_completion(prompt)
        title = title.replace('"','')

        #Account for a response that has multiple lines:
        if '\n' in title:
            new_title = title.replace('\n','/ ')
            title = new_title[:50] + '...'

        return title

    #gpt-3.5-turbo
    def get_completion(prompt, model="gpt-3.5-turbo"):
        messages = [{"role": "user", "content": prompt}]
                
        retry_limit = 3
        retry_interval = 30
        retry_count = 0
        #limit size of prompt
        while retry_count < retry_limit:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens = 3000,
                    temperature=0, # this is the degree of randomness of the model's output
                )
                retry_count = retry_limit
                
            except Exception as e:
                print(f"An error occurred: {str(e)}")
                retry_count += 1
                if retry_count < retry_limit:
                    print(f"Retrying in {retry_interval} seconds...")
                    time.sleep(retry_interval)
                else:
                    print("Exceeded retry limit. Skipping...")
                    response = "ERROR"
        #print(response.choices[0].message)
        return response.choices[0].message.content
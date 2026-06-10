"""
US Residential Intelligence v2 — collector.py
수집 전용. RSS 파싱 → 중복 제거 → articles.csv append.
분류는 classifier.py가 담당.
"""

import csv
import hashlib
import os
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from html import unescape

from dotenv import load_dotenv

load_dotenv()

# Windows cp949 터미널에서 한글·특수문자 출력 가능하도록
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------------
# 1. 설정
# ------------------------------------------------------------------

ARTICLES_CSV = "articles.csv"

CSV_COLUMNS = [
    "article_id", "collected_at", "published_at", "source",
    "title", "url", "summary", "classified",
    "category", "event_tags", "signal_type", "sector",
    "woomi_relevance", "claude_rationale", "access_limited",
]

RSS_FEEDS = [
    # 코어 — Multifamily
    {"source": "Multifamily Dive",       "url": "https://www.multifamilydive.com/feeds/news/",           "sector": "Multifamily"},
    {"source": "Multifamily Executive",  "url": "https://www.multifamilyexecutive.com/rss.xml",           "sector": "Multifamily"},
    {"source": "Multi-Housing News",     "url": "https://www.multihousingnews.com/feed/",                 "sector": "Multifamily"},
    {"source": "YieldPro",               "url": "https://yieldpro.com/feed/",                             "sector": "Multifamily"},
    {"source": "GlobeSt",                "url": "https://www.globest.com/feed/",                          "sector": "CRE"},
    {"source": "Bisnow",                 "url": "https://www.bisnow.com/rss",                             "sector": "CRE"},
    {"source": "Commercial Observer",    "url": "https://commercialobserver.com/feed/",                   "sector": "CRE"},
    {"source": "Connect CRE",            "url": "https://www.connectcre.com/feed/",                       "sector": "CRE"},
    {"source": "The Real Deal",          "url": "https://therealdeal.com/feed/",                          "sector": "CRE"},
    {"source": "Eye on Housing (NAHB)",  "url": "https://eyeonhousing.org/category/multifamily/feed/",    "sector": "Multifamily"},
    # 협회·정책
    {"source": "NMHC",                   "url": "https://www.nmhc.org/news/rss/",                         "sector": "Policy"},
    {"source": "Urban Land Institute",   "url": "https://urbanland.uli.org/feed/",                        "sector": "Policy"},
    {"source": "Federal Reserve",        "url": "https://www.federalreserve.gov/feeds/press_all.xml",     "sector": "Macro"},
    # 자본·금융
    {"source": "Walker & Dunlop",        "url": "https://www.walkerdunlop.com/insights/feed/",            "sector": "Capital"},
    {"source": "Berkadia",               "url": "https://berkadia.com/feed/",                             "sector": "Capital"},
    # 지역 — Sun Belt + West Coast
    {"source": "Connect CRE Texas",       "url": "https://www.connectcre.com/feed?story-market=texas",          "sector": "Multifamily"},
    {"source": "Connect CRE South FL",    "url": "https://www.connectcre.com/feed?story-market=south-florida",  "sector": "Multifamily"},
    {"source": "Connect CRE Phoenix",     "url": "https://www.connectcre.com/feed?story-market=phoenix",        "sector": "Multifamily"},
    {"source": "Connect CRE Atlanta",     "url": "https://www.connectcre.com/feed?story-market=atlanta",        "sector": "Multifamily"},
    {"source": "Connect CRE Charlotte",   "url": "https://www.connectcre.com/feed?story-market=charlotte",      "sector": "Multifamily"},
    {"source": "Connect CRE Seattle",    "url": "https://www.connectcre.com/region/seattle/feed",               "sector": "Multifamily"},
    {"source": "Connect CRE Denver",     "url": "https://www.connectcre.com/region/denver/feed",                "sector": "Multifamily"},
    {"source": "Connect CRE California", "url": "https://www.connectcre.com/region/california/feed",            "sector": "Multifamily"},
    {"source": "Yardi Matrix Blog",      "url": "https://www.yardimatrix.com/blog/feed",                        "sector": "Multifamily"},
    {"source": "LA Urbanize",             "url": "https://la.urbanize.city/rss.xml",                            "sector": "Residential"},
    {"source": "California YIMBY",        "url": "https://californiayimby.com/feed",                            "sector": "Policy"},
    {"source": "SF YIMBY",                "url": "https://sfyimby.com/feed",                                    "sector": "Policy"},
]

BLUE_VISTA_UNIVERSITIES = [
    {"name": "Brigham Young University",                                   "city": "Provo",            "state": "UT", "bv_rank": 1},
    {"name": "University of California - Los Angeles",                     "city": "Los Angeles",      "state": "CA", "bv_rank": 2},
    {"name": "Virginia Polytechnic Institute and State University",        "city": "Blacksburg",       "state": "VA", "bv_rank": 3},
    {"name": "University of Florida",                                      "city": "Gainesville",      "state": "FL", "bv_rank": 4},
    {"name": "New York University",                                        "city": "New York",         "state": "NY", "bv_rank": 5},
    {"name": "University of Illinois - Urbana-Champaign",                 "city": "Champaign",        "state": "IL", "bv_rank": 6},
    {"name": "Rutgers University - New Brunswick",                         "city": "Highland Park",    "state": "NJ", "bv_rank": 7},
    {"name": "University of Alabama",                                      "city": "Tuscaloosa",       "state": "AL", "bv_rank": 8},
    {"name": "University of Missouri",                                     "city": "Columbia",         "state": "MO", "bv_rank": 9},
    {"name": "University of Kansas",                                       "city": "Lawrence",         "state": "KS", "bv_rank": 10},
    {"name": "Oklahoma State University",                                  "city": "Stillwater",       "state": "OK", "bv_rank": 11},
    {"name": "Stony Brook University",                                     "city": "Stony Brook",      "state": "NY", "bv_rank": 11},
    {"name": "Stanford University",                                        "city": "Palo Alto",        "state": "CA", "bv_rank": 13},
    {"name": "Columbia University",                                        "city": "New York",         "state": "NY", "bv_rank": 13},
    {"name": "University of Wisconsin - Madison",                          "city": "Madison",          "state": "WI", "bv_rank": 13},
    {"name": "Oregon State University",                                    "city": "Corvallis",        "state": "OR", "bv_rank": 16},
    {"name": "University of Iowa",                                         "city": "Iowa City",        "state": "IA", "bv_rank": 16},
    {"name": "Pennsylvania State University",                              "city": "University Park",  "state": "PA", "bv_rank": 16},
    {"name": "James Madison University",                                   "city": "Harrisonburg",     "state": "VA", "bv_rank": 19},
    {"name": "Cornell University",                                         "city": "Ithaca",           "state": "NY", "bv_rank": 20},
    {"name": "Purdue University",                                          "city": "West Lafayette",   "state": "IN", "bv_rank": 20},
    {"name": "University of California - Irvine",                         "city": "Irvine",           "state": "CA", "bv_rank": 22},
    {"name": "University of Georgia",                                      "city": "Athens",           "state": "GA", "bv_rank": 22},
    {"name": "University of Washington",                                   "city": "Seattle",          "state": "WA", "bv_rank": 22},
    {"name": "University of Pittsburgh",                                   "city": "Pittsburgh",       "state": "PA", "bv_rank": 25},
    {"name": "Iowa State University",                                      "city": "Ames",             "state": "IA", "bv_rank": 26},
    {"name": "University of North Carolina",                               "city": "Chapel Hill",      "state": "NC", "bv_rank": 27},
    {"name": "University of Central Florida",                              "city": "Orlando",          "state": "FL", "bv_rank": 28},
    {"name": "Michigan State University",                                  "city": "East Lansing",     "state": "MI", "bv_rank": 29},
    {"name": "San Diego State University",                                 "city": "San Diego",        "state": "CA", "bv_rank": 30},
    {"name": "Texas A&M University",                                       "city": "College Station",  "state": "TX", "bv_rank": 31},
    {"name": "Florida State University",                                   "city": "Tallahassee",      "state": "FL", "bv_rank": 32},
    {"name": "Auburn University",                                          "city": "Auburn",           "state": "AL", "bv_rank": 33},
    {"name": "University of Texas at Austin",                              "city": "Austin",           "state": "TX", "bv_rank": 34},
    {"name": "Kansas State University",                                    "city": "Manhattan",        "state": "KS", "bv_rank": 35},
    {"name": "University of Arizona",                                      "city": "Tucson",           "state": "AZ", "bv_rank": 36},
    {"name": "Rochester Institute Of Technology",                          "city": "Rochester",        "state": "NY", "bv_rank": 37},
    {"name": "Florida Atlantic University - Boca Raton",                   "city": "Boca Raton",       "state": "FL", "bv_rank": 37},
    {"name": "University of Oklahoma",                                     "city": "Norman",           "state": "OK", "bv_rank": 37},
    {"name": "Duke University",                                            "city": "Durham",           "state": "NC", "bv_rank": 40},
    {"name": "University of Kentucky",                                     "city": "Lexington",        "state": "KY", "bv_rank": 40},
    {"name": "University of Connecticut",                                  "city": "Storrs",           "state": "CT", "bv_rank": 42},
    {"name": "University of California - Riverside",                      "city": "Riverside",        "state": "CA", "bv_rank": 42},
    {"name": "Indiana University",                                         "city": "Bloomington",      "state": "IN", "bv_rank": 44},
    {"name": "Northeastern University",                                    "city": "Boston",           "state": "MA", "bv_rank": 45},
    {"name": "Mississippi State University",                               "city": "Starkville",       "state": "MS", "bv_rank": 46},
    {"name": "Boston College",                                             "city": "Newton",           "state": "MA", "bv_rank": 47},
    {"name": "Bowling Green State University",                             "city": "Bowling Green",    "state": "OH", "bv_rank": 48},
    {"name": "University of Maryland",                                     "city": "College Park",     "state": "MD", "bv_rank": 49},
    {"name": "University of Utah",                                         "city": "Salt Lake City",   "state": "UT", "bv_rank": 50},
    {"name": "University of Houston",                                      "city": "Houston",          "state": "TX", "bv_rank": 50},
    {"name": "University of Delaware",                                     "city": "Newark",           "state": "DE", "bv_rank": 52},
    {"name": "Florida International University",                           "city": "Miami",            "state": "FL", "bv_rank": 53},
    {"name": "Appalachian State University",                               "city": "Boone",            "state": "NC", "bv_rank": 54},
    {"name": "University of Nebraska - Lincoln",                           "city": "Lincoln",          "state": "NE", "bv_rank": 54},
    {"name": "University of Tennessee",                                    "city": "Knoxville",        "state": "TN", "bv_rank": 56},
    {"name": "Massachusetts Institute of Technology",                      "city": "Cambridge",        "state": "MA", "bv_rank": 57},
    {"name": "University of Virginia",                                     "city": "Charlottesville",  "state": "VA", "bv_rank": 57},
    {"name": "California State Polytechnic University - Pomona",           "city": "Pomona",           "state": "CA", "bv_rank": 57},
    {"name": "George Mason University",                                    "city": "Fairfax",          "state": "VA", "bv_rank": 57},
    {"name": "University of Mississippi",                                  "city": "Oxford",           "state": "MS", "bv_rank": 61},
    {"name": "Harvard University",                                         "city": "Cambridge",        "state": "MA", "bv_rank": 61},
    {"name": "Kennesaw State University",                                  "city": "Kennesaw",         "state": "GA", "bv_rank": 61},
    {"name": "University of South Carolina",                               "city": "Columbia",         "state": "SC", "bv_rank": 61},
    {"name": "Florida Gulf Coast University",                              "city": "Fort Myers",       "state": "FL", "bv_rank": 65},
    {"name": "University of Massachusetts",                                "city": "Amherst",          "state": "MA", "bv_rank": 66},
    {"name": "Western Carolina University",                                "city": "Cullowhee",        "state": "NC", "bv_rank": 67},
    {"name": "Utah State University",                                      "city": "Logan",            "state": "UT", "bv_rank": 68},
    {"name": "University of Arkansas",                                     "city": "Fayetteville",     "state": "AR", "bv_rank": 69},
    {"name": "Clemson University",                                         "city": "Clemson",          "state": "SC", "bv_rank": 69},
    {"name": "West Virginia University",                                   "city": "Morgantown",       "state": "WV", "bv_rank": 71},
    {"name": "New Mexico State University",                                "city": "Las Cruces",       "state": "NM", "bv_rank": 72},
    {"name": "California State University - Fresno",                       "city": "Fresno",           "state": "CA", "bv_rank": 72},
    {"name": "Minnesota State University - Mankato",                       "city": "Mankato",          "state": "MN", "bv_rank": 74},
    {"name": "Baylor University",                                          "city": "Waco",             "state": "TX", "bv_rank": 74},
    {"name": "University of North Carolina - Wilmington",                  "city": "Wilmington",       "state": "NC", "bv_rank": 76},
    {"name": "University of Miami",                                        "city": "Miami",            "state": "FL", "bv_rank": 76},
    {"name": "Louisiana State University",                                 "city": "Baton Rouge",      "state": "LA", "bv_rank": 76},
    {"name": "Georgetown University",                                      "city": "Washington",       "state": "DC", "bv_rank": 79},
    {"name": "East Tennessee State University",                            "city": "Johnson City",     "state": "TN", "bv_rank": 80},
    {"name": "Texas Christian University",                                 "city": "Fort Worth",       "state": "TX", "bv_rank": 80},
    {"name": "Emory University",                                           "city": "Atlanta",          "state": "GA", "bv_rank": 80},
    {"name": "University of Pennsylvania",                                 "city": "Philadelphia",     "state": "PA", "bv_rank": 83},
    {"name": "North Carolina A&T State University",                        "city": "Greensboro",       "state": "NC", "bv_rank": 84},
    {"name": "North Carolina State University",                            "city": "Raleigh",          "state": "NC", "bv_rank": 85},
    {"name": "Western Washington University",                              "city": "Bellingham",       "state": "WA", "bv_rank": 86},
    {"name": "California State University - Fullerton",                    "city": "Fullerton",        "state": "CA", "bv_rank": 87},
    {"name": "University at Buffalo - State University of New York",       "city": "Buffalo",          "state": "NY", "bv_rank": 87},
    {"name": "University of Colorado - Boulder",                           "city": "Boulder",          "state": "CO", "bv_rank": 89},
    {"name": "Boston University",                                          "city": "Boston",           "state": "MA", "bv_rank": 90},
    {"name": "University of California - Davis",                           "city": "Davis",            "state": "CA", "bv_rank": 90},
    {"name": "University of Texas - Rio Grande Valley - Edinburg Campus",  "city": "Edinburg",         "state": "TX", "bv_rank": 92},
    {"name": "Savannah College of Art & Design",                           "city": "Savannah",         "state": "GA", "bv_rank": 93},
    {"name": "Kent State University",                                      "city": "Kent",             "state": "OH", "bv_rank": 93},
    {"name": "Texas State University",                                     "city": "San Marcos",       "state": "TX", "bv_rank": 93},
    {"name": "University of Notre Dame",                                   "city": "South Bend",       "state": "IN", "bv_rank": 96},
    {"name": "Georgia Southern University",                                "city": "Statesboro",       "state": "GA", "bv_rank": 97},
    {"name": "Middle Tennessee State University",                          "city": "Murfreesboro",     "state": "TN", "bv_rank": 98},
    {"name": "University of New Mexico",                                   "city": "Albuquerque",      "state": "NM", "bv_rank": 98},
    {"name": "University of North Carolina - Greensboro",                  "city": "Greensboro",       "state": "NC", "bv_rank": 100},
    {"name": "Illinois State University",                                  "city": "Normal",           "state": "IL", "bv_rank": 100},
    {"name": "Towson University",                                          "city": "Towson",           "state": "MD", "bv_rank": 102},
    {"name": "University of North Carolina - Charlotte",                   "city": "Charlotte",        "state": "NC", "bv_rank": 102},
    {"name": "University of California - Berkeley",                       "city": "Berkeley",         "state": "CA", "bv_rank": 104},
    {"name": "University of Southern California",                          "city": "Los Angeles",      "state": "CA", "bv_rank": 105},
    {"name": "University of Nevada - Las Vegas",                           "city": "Las Vegas",        "state": "NV", "bv_rank": 106},
    {"name": "University of Minnesota",                                    "city": "Minneapolis",      "state": "MN", "bv_rank": 106},
    {"name": "University of Texas at San Antonio",                         "city": "San Antonio",      "state": "TX", "bv_rank": 108},
    {"name": "Grand Valley State University - Allendale Campus",           "city": "Allendale",        "state": "MI", "bv_rank": 109},
    {"name": "University of Oregon",                                       "city": "Eugene",           "state": "OR", "bv_rank": 110},
    {"name": "Coastal Carolina University",                                "city": "Conway",           "state": "SC", "bv_rank": 111},
    {"name": "Texas Tech University",                                      "city": "Lubbock",          "state": "TX", "bv_rank": 111},
    {"name": "California State University - Chico",                        "city": "Chico",            "state": "CA", "bv_rank": 113},
    {"name": "San Jose State University",                                  "city": "San Jose",         "state": "CA", "bv_rank": 113},
    {"name": "Colorado State University",                                  "city": "Fort Collins",     "state": "CO", "bv_rank": 113},
    {"name": "University of Louisville",                                   "city": "Louisville",       "state": "KY", "bv_rank": 116},
    {"name": "Syracuse University",                                        "city": "Syracuse",         "state": "NY", "bv_rank": 117},
    {"name": "University of Tennessee - Chattanooga",                      "city": "Chattanooga",      "state": "TN", "bv_rank": 118},
    {"name": "Montana State University",                                   "city": "Bozeman",          "state": "MT", "bv_rank": 118},
    {"name": "Ohio University",                                            "city": "Athens",           "state": "OH", "bv_rank": 118},
    {"name": "Drexel University",                                          "city": "Philadelphia",     "state": "PA", "bv_rank": 121},
    {"name": "Wichita State University",                                   "city": "Wichita",          "state": "KS", "bv_rank": 122},
    {"name": "University of New Hampshire",                                "city": "Durham",           "state": "NH", "bv_rank": 123},
    {"name": "Ball State University",                                      "city": "Muncie",           "state": "IN", "bv_rank": 123},
    {"name": "University of Hawaii at Manoa",                              "city": "Honolulu",         "state": "HI", "bv_rank": 123},
    {"name": "University of North Texas",                                  "city": "Denton",           "state": "TX", "bv_rank": 126},
    {"name": "Temple University",                                          "city": "Philadelphia",     "state": "PA", "bv_rank": 127},
    {"name": "University of South Florida",                                "city": "Tampa",            "state": "FL", "bv_rank": 127},
    {"name": "University of South Alabama",                                "city": "Mobile",           "state": "AL", "bv_rank": 129},
    {"name": "Saint Louis University",                                     "city": "St Louis",         "state": "MO", "bv_rank": 129},
    {"name": "Utah Valley University",                                     "city": "Orem",             "state": "UT", "bv_rank": 129},
    {"name": "California State University - Northridge",                   "city": "Northridge",       "state": "CA", "bv_rank": 129},
    {"name": "University of Illinois - Chicago",                           "city": "Chicago",          "state": "IL", "bv_rank": 133},
    {"name": "Binghamton University - State University of New York",       "city": "Binghamton",       "state": "NY", "bv_rank": 134},
    {"name": "University of California - Santa Cruz",                      "city": "Santa Cruz",       "state": "CA", "bv_rank": 135},
    {"name": "University of Texas - Rio Grande Valley - Brownsville Campus","city": "Brownsville",     "state": "TX", "bv_rank": 136},
    {"name": "College of Charleston",                                      "city": "Charleston",       "state": "SC", "bv_rank": 137},
    {"name": "University of Texas at Dallas",                              "city": "Richardson",       "state": "TX", "bv_rank": 137},
    {"name": "Old Dominion University",                                    "city": "Norfolk",          "state": "VA", "bv_rank": 139},
    {"name": "Miami University",                                           "city": "Oxford",           "state": "OH", "bv_rank": 139},
    {"name": "University of California - Santa Barbara",                   "city": "Santa Barbara",    "state": "CA", "bv_rank": 141},
    {"name": "Tarleton State University",                                  "city": "Stephenville",     "state": "TX", "bv_rank": 142},
    {"name": "Ohio State University",                                      "city": "Columbus",         "state": "OH", "bv_rank": 142},
    {"name": "University of Michigan",                                     "city": "Ann Arbor",        "state": "MI", "bv_rank": 142},
    {"name": "Boise State University",                                     "city": "Boise",            "state": "ID", "bv_rank": 145},
    {"name": "Georgia Institute of Technology",                            "city": "Atlanta",          "state": "GA", "bv_rank": 146},
    {"name": "California State University - Los Angeles",                  "city": "Los Angeles",      "state": "CA", "bv_rank": 147},
    {"name": "George Washington University",                               "city": "Washington",       "state": "DC", "bv_rank": 148},
    {"name": "Arizona State University",                                   "city": "Tempe",            "state": "AZ", "bv_rank": 149},
    {"name": "Washington State University",                                "city": "Pullman",          "state": "WA", "bv_rank": 150},
    {"name": "University of Nevada - Reno",                                "city": "Reno",             "state": "NV", "bv_rank": 151},
    {"name": "Sam Houston State University",                               "city": "Huntsville",       "state": "TX", "bv_rank": 152},
    {"name": "California State University - San Bernardino",               "city": "San Bernardino",   "state": "CA", "bv_rank": 153},
    {"name": "University of Southern Mississippi",                         "city": "Hattiesburg",      "state": "MS", "bv_rank": 154},
    {"name": "Portland State University",                                  "city": "Portland",         "state": "OR", "bv_rank": 154},
    {"name": "Georgia State University",                                   "city": "Atlanta",          "state": "GA", "bv_rank": 154},
    {"name": "Central Michigan University",                                "city": "Mount Pleasant",   "state": "MI", "bv_rank": 157},
    {"name": "East Carolina University",                                   "city": "Greenville",       "state": "NC", "bv_rank": 157},
    {"name": "California State University - Sacramento",                   "city": "Sacramento",       "state": "CA", "bv_rank": 157},
    {"name": "University of Vermont",                                      "city": "Burlington",       "state": "VT", "bv_rank": 160},
    {"name": "Missouri State University",                                  "city": "Springfield",      "state": "MO", "bv_rank": 160},
    {"name": "University of Alabama at Birmingham",                        "city": "Birmingham",       "state": "AL", "bv_rank": 162},
    {"name": "University of Wisconsin - Milwaukee",                        "city": "Milwaukee",        "state": "WI", "bv_rank": 163},
    {"name": "Virginia Commonwealth University",                           "city": "Richmond",         "state": "VA", "bv_rank": 164},
    {"name": "University of Texas at Arlington",                           "city": "Arlington",        "state": "TX", "bv_rank": 165},
    {"name": "Wayne State University",                                     "city": "Detroit",          "state": "MI", "bv_rank": 166},
    {"name": "University of Cincinnati",                                   "city": "Cincinnati",       "state": "OH", "bv_rank": 167},
    {"name": "Northern Arizona University",                                "city": "Flagstaff",        "state": "AZ", "bv_rank": 168},
    {"name": "Western Michigan University",                                "city": "Kalamazoo",        "state": "MI", "bv_rank": 169},
    {"name": "University of Memphis",                                      "city": "Memphis",          "state": "TN", "bv_rank": 170},
    {"name": "Western Kentucky University",                                "city": "Bowling Green",    "state": "KY", "bv_rank": 171},
    {"name": "University of Toledo",                                       "city": "Toledo",           "state": "OH", "bv_rank": 172},
    {"name": "University of Akron",                                        "city": "Akron",            "state": "OH", "bv_rank": 173},
    {"name": "Indiana University - Purdue University Indianapolis",        "city": "Indianapolis",     "state": "IN", "bv_rank": 173},
    {"name": "Cleveland State University",                                 "city": "Cleveland",        "state": "OH", "bv_rank": 175},
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WoomiGlobalResearchBot/2.0)"
}
FETCH_TIMEOUT = 15  # seconds


# ------------------------------------------------------------------
# 2. RSS 수집
# ------------------------------------------------------------------


def _make_google_news_rss_url(university_name: str) -> str:
    """대학명 + 'student housing'으로 Google News RSS URL 생성."""
    query = f'"{university_name}" student housing'
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"


def fetch_student_housing_feed(university: dict) -> list[dict]:
    """대학별 Google News RSS 수집. sector = 'Student Housing' 고정."""
    name = university["name"]
    url = _make_google_news_rss_url(name)
    source_label = f"Student Housing — {name} ({university['state']})"
    try:
        feed = feedparser.parse(url, request_headers=REQUEST_HEADERS)
    except Exception as e:
        print(f"    [SKIP] {name} — feedparser 오류: {e}")
        return []
    cutoff = datetime.now() - timedelta(days=90)  # 90일 이내 기사만 수집
    articles = []
    for entry in feed.entries[:5]:
        title = _clean_html(entry.get("title", "")).strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        published_str = _parse_published(entry)
        if datetime.strptime(published_str, "%Y-%m-%d %H:%M:%S") < cutoff:
            continue
        raw_summary = (
            entry.get("summary")
            or (entry.get("content", [{}])[0].get("value", ""))
        )
        summary = _clean_html(raw_summary)[:400]
        articles.append({
            "article_id":       make_article_id(link),
            "collected_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "published_at":     published_str,
            "source":           source_label,
            "title":            title,
            "url":              link,
            "summary":          summary,
            "classified":       False,
            "category":         "",
            "event_tags":       "",
            "signal_type":      "",
            "sector":           "Student Housing",
            "woomi_relevance":  "",
            "claude_rationale": "",
            "access_limited":   False,  # Google News RSS: title이 실질 콘텐츠
        })
    return articles

def _clean_html(raw: str) -> str:
    return BeautifulSoup(unescape(raw or ""), "html.parser").get_text(separator=" ").strip()


def _parse_published(entry) -> str:
    """published 날짜 파싱. 실패 시 또는 1990년 이전 날짜는 오늘 날짜 반환."""
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            dt = datetime(*t[:6])
            if dt.year < 1990:
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_feed(source: str, url: str, sector: str) -> list[dict]:
    try:
        feed = feedparser.parse(url, request_headers=REQUEST_HEADERS)
    except Exception as e:
        print(f"  [SKIP] {source} — feedparser 오류: {e}")
        return []

    cutoff = datetime.now() - timedelta(days=90)  # 90일 이내 기사만 수집
    articles = []
    for entry in feed.entries:
        title = _clean_html(entry.get("title", "")).strip()
        link  = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        published_str = _parse_published(entry)
        if datetime.strptime(published_str, "%Y-%m-%d %H:%M:%S") < cutoff:
            continue

        # summary: description 우선, 없으면 content
        raw_summary = (
            entry.get("summary")
            or (entry.get("content", [{}])[0].get("value", ""))
        )
        summary = _clean_html(raw_summary)[:400]

        access_limited = _judge_access_limited(source, link, summary)

        articles.append({
            "article_id":    make_article_id(link),
            "collected_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "published_at":  published_str,
            "source":        source,
            "title":         title,
            "url":           link,
            "summary":       summary,
            "classified":    False,
            "category":      "",
            "event_tags":    "",
            "signal_type":   "",
            "sector":        sector,
            "woomi_relevance": "",
            "claude_rationale": "",
            "access_limited": access_limited,
        })
    return articles


# 소스별 access_limited 판정
_FREE_SOURCES = {
    "Federal Reserve", "NMHC", "Urban Land Institute",
    "Eye on Housing (NAHB)", "Yardi Matrix Blog",
}
_FETCH_SOURCES = {"LA Urbanize", "Bisnow", "The Real Deal"}


def _judge_access_limited(source: str, url: str, summary: str) -> bool:
    if source in _FREE_SOURCES:
        return False
    if source in _FETCH_SOURCES:
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=5)
            text = BeautifulSoup(resp.text, "html.parser").get_text(separator=" ")
            return len(text.strip()) < 300
        except Exception:
            return len(summary) < 100  # fallback
    return len(summary) < 100


# ------------------------------------------------------------------
# 3. 중복 제거
# ------------------------------------------------------------------

def make_article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def load_existing_ids() -> set:
    if not os.path.exists(ARTICLES_CSV):
        return set()
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return {row["article_id"] for row in reader}


# ------------------------------------------------------------------
# 4. CSV 저장
# ------------------------------------------------------------------

def save_articles(articles: list[dict]) -> None:
    file_exists = os.path.exists(ARTICLES_CSV)
    with open(ARTICLES_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(articles)


# ------------------------------------------------------------------
# 5. 실행
# ------------------------------------------------------------------

def main():
    print(f"=== US Residential Intelligence v2 — Collector ===")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    existing_ids = load_existing_ids()
    print(f"기존 누적 기사: {len(existing_ids)}건\n")

    total_fetched = 0
    total_skipped = 0
    new_articles  = []

    # ------------------------------------------------------------------
    # STEP 1: Student Housing — Blue Vista 175개 대학 Google News RSS
    # ------------------------------------------------------------------
    print(f"[STEP 1] Student Housing 수집 ({len(BLUE_VISTA_UNIVERSITIES)}개 대학)")
    sh_fetched = 0
    sh_new     = 0

    for i, univ in enumerate(BLUE_VISTA_UNIVERSITIES, start=1):
        print(f"  [{i}/{len(BLUE_VISTA_UNIVERSITIES)}] BV#{univ['bv_rank']} {univ['name']}")
        fetched = fetch_student_housing_feed(univ)
        sh_fetched += len(fetched)
        total_fetched += len(fetched)

        for article in fetched:
            if article["article_id"] in existing_ids:
                total_skipped += 1
            else:
                existing_ids.add(article["article_id"])
                new_articles.append(article)
                sh_new += 1

        time.sleep(0.5)

    print(f"\n  → Student Housing 수집: {sh_fetched}건 / 신규: {sh_new}건\n")

    # ------------------------------------------------------------------
    # STEP 2: 기존 RSS 피드
    # ------------------------------------------------------------------
    print(f"[STEP 2] RSS 피드 수집 ({len(RSS_FEEDS)}개 소스)")
    for feed in RSS_FEEDS:
        source = feed["source"]
        url    = feed["url"]
        sector = feed["sector"]
        print(f"  수집 중: {source}")

        fetched = fetch_feed(source, url, sector)
        total_fetched += len(fetched)

        for article in fetched:
            if article["article_id"] in existing_ids:
                total_skipped += 1
            else:
                existing_ids.add(article["article_id"])
                new_articles.append(article)

    if new_articles:
        save_articles(new_articles)

    print(f"\n--- 수집 완료 ---")
    print(f"  전체 수집: {total_fetched}건")
    print(f"  중복 skip: {total_skipped}건")
    print(f"  신규 저장: {len(new_articles)}건  (Student Housing 신규: {sh_new}건)")
    print(f"  → {ARTICLES_CSV}")


if __name__ == "__main__":
    main()

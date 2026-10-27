Things we should make

filters for major, year, college 

"groups": group classes by major, typical year taken 


edge cases: certificates & minors: taken at weird random times, less people taking them

how to represent busy time: array of 8am-9pm for Sunday-Saturday
x coordinates hour, y coordinates day

availability= [
    [0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0]
]

0 = means free
1 = means busy

note: if we collect syllabi, we know when each class has exams (ballpark)

rethink how to represent free/busy, a value for eac hour doesn't work, not enough precision, becuase of classes starting adn ending at 10, 15, 20, 30, 45

0 = free whole time 
1 = busy 0-15
2 = busy 0-30
3 = busy 0-45
4 = busy 0-60
5 = busy 15-60
6 = busy 30-60
7 = busy 45-60


{
      "course_id": "PSY200-LEC-01",
      "course_code": "PSY 200",
      "course_name": "Introduction to Cognitive Psychology",
      "section": "LEC-01",
      "capacity": 110,
      "open_seats": 12,
      "meetings": [
        {
          "days": [
            "Monday",
            "Wednesday"
          ],
          "start_time": "12:30",
          "end_time": "13:45"
          "busy": [1][5.5] and [3][6.45]
        }
      ]
    },


get time handling library to manage times free and busy 

    do [][][] with specifc array for free time 
    or do [][] with complicated free time (0-7)
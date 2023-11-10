# PNSN_staticMap

This is very early stages of creating a real time seismic data map using folium

Imports Required Modules:

The script imports necessary Python modules for handling HTTP requests, JSON data, threading, file I/O, and other utilities.
It also imports specific functions and classes from the obspy library, which is used for processing seismological data.
Defines User Agents:

A list of user-agent strings is defined to mimic different web browsers when making HTTP requests.
Makes an HTTP Request:

The script fetches seismic data in JSON format from a predefined URL using the requests library, selecting a random user-agent from the list.
JSON File Handling:

It contains a function to save JSON data to a file.
Another function updates an existing JSON file with trace data from a seismic data stream.
SeedLink Connection Handling:

A SeedLinkException class is defined to handle SeedLink-specific errors.
The SeedlinkUpdater class extends the SLClient class from the obspy library, providing functionality to connect to a SeedLink server, process data packets, and manage the data stream.
Threading for Data Processing:

The script uses a separate thread to run the SeedLink client to collect seismic data continuously without blocking the main program.
Data Processing:

It processes packets of seismic data, adding them to a stream and merging overlapping traces.
The script prints the stream data and updates the JSON file with new trace data in a loop, with a 2-second pause between iterations.
Utility Functions:

There are utility functions to parse time strings with suffixes to seconds or minutes.
Main Program Logic:

The main function coordinates the execution flow, checking the HTTP response status, saving the JSON data to a file, initializing the SeedLink client, and starting the data collection in a thread.
It includes a console-based loop that can be interrupted with a keyboard signal to stop the SeedLink client thread and close the connection gracefully.
Error Handling and Cleanup:

The script attempts to handle errors and exceptions that may occur during execution.
It ensures that the SeedLink connection is closed properly when the program is interrupted or when an exception occurs.

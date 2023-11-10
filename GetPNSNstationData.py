# -*- coding: utf-8 -*-
"""
Created on Wed Nov  8 17:26:51 2023

@author: slugn
"""


from obspy import Stream
from obspy.core import UTCDateTime
from threading import Event
import threading
import time
import os
import sys
import requests
import json
import random
from obspy import read
import logging
import folium
from folium.plugins import HeatMapWithTime
from collections import defaultdict

from obspy.clients.seedlink.slpacket import SLPacket
from obspy.clients.seedlink import SLClient


user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
    # Add more user agents as needed
]

url = 'http://quickshake.pnsn.org/scnls'

headers = {'User-Agent': random.choice(user_agents)}
response = requests.get(url, headers=headers)



def save_SCNLS_json_to_file(json_data, file_name):
    with open(file_name, 'w') as file:
        json.dump(json_data, file, indent=4)


def update_json_with_trace_data(json_file_name, stream):
    # Load the existing JSON data
    try:
        with open(json_file_name, 'r') as file:
            scnls_data = json.load(file)
    except FileNotFoundError:
        logging.error(f"File {json_file_name} not found.")
     
        # Determine the overall time span
   overall_start = min(trace.stats.starttime for trace in stream)
   overall_end = max(trace.stats.endtime for trace in stream)   
     
        # Interpolate the stream to the desired sampling rate
    interpolated_stream = Stream()
    
    for trace in stream:
        trace.detrend("demean") # Remove mean to avoid edge effects during interpolation
        trace.interpolate(sampling_rate = 100, method='lanczos', a=20, npts = 1000)
        interpolated_stream.append(trace)    
            
    # Convert the ObsPy Stream object to a JSON-serializable structure
    for trace in stream:
        trace.normalize()  # Ensure trace is normalized
        trace.stats.processing = []
        
        average_value = sum(trace.data) / len(trace.data) #average the data for map

        # Find the matching JSON object by some identifier, e.g., 'sta'
        match = next((item for item in scnls_data if item['sta'] == trace.stats.station), None)
        if match:
            # Update the match with the new trace data
            match['data'] = trace.data.tolist()
            match['data_average'] = average_value
        else:
            # If no match is found, add a new entry (or handle as appropriate)
            logging.error("no match found")
    
    # Write the updated JSON data back to the file
    with open(json_file_name, 'w') as file:
        json.dump(scnls_data, file, indent=4)



class SeedLinkException(Exception):
    """
    SeedLink error.
    """
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

class SeedlinkUpdater(SLClient):

    def __init__(self, stream, lock=None):
        super(SeedlinkUpdater, self).__init__()
        self.stream = stream
        self.lock = lock     
        self.stop_event = threading.Event()  # Initialize the stop_event
        self.packet_counts = defaultdict(int)  # Initialize the packet counter
        self.expected_stations = set() # Add all expected station IDs to this set
          
    def run(self, packet_handler=None):
        """
        Start this SLClient.

        :type packet_handler: callable
        :param packet_handler: Custom packet handler funtion to override
            `self.packet_handler` for this seedlink request. The function will
            be repeatedly called with two arguments: the current packet counter
            (`int`) and the currently served seedlink packet
            (:class:`~obspy.clients.seedlink.slclient.SLPacket`). The
            function should return `True` to abort the request or `False` to
             continue the request.
        """
        while not self.stop_event.is_set():
            if packet_handler is None:
                packet_handler = self.packet_handler
            if self.infolevel is not None:
                self.slconn.request_info(self.infolevel)
            # Loop with the connection manager
            count = 1
            slpack = self.slconn.collect()
            while slpack is not None:
                if (slpack == SLPacket.SLTERMINATE):
                    break
                try:
                    # do something with packet
                    terminate = packet_handler(count, slpack)
                    if terminate:
                        break
                except SeedLinkException as sle:
                    logging.error(self.__class__.__name__ + ": " + sle.value)
                if count >= sys.maxsize:
                    count = 1
                    logging.info("DEBUG INFO: " + self.__class__.__name__ + ":", end=' ')
                    logging.info("Packet count reset to 1")
                else:
                    count += 1
                slpack = self.slconn.collect()
                
                if self.stop_event.is_set():  # Check the stop_event before blocking operations
                    break

        # Close the SeedLinkConnection
        self.slconn.close()
        logging.info("run method closed")
        print("run method closed")
     
     
    def packet_handler(self, count, slpack):
        """
        for compatibility with obspy 0.10.3 renaming
        """
        self.packetHandler(count, slpack)

    def packetHandler(self, count, slpack):
        """
        Processes each packet received from the SeedLinkConnection.
        :type count: int
        :param count:  Packet counter.
        :type slpack: :class:`~obspy.seedlink.SLPacket`
        :param slpack: packet to process.
        :return: Boolean true if connection to SeedLink server should be
            closed and session terminated, false otherwise.
        """

        # check if not a complete packet
        if slpack is None or (slpack == SLPacket.SLNOPACKET) or \
                (slpack == SLPacket.SLERROR):
            return False

        # get basic packet info
        type = slpack.get_type()

        # process INFO packets here
        if type == SLPacket.TYPE_SLINF:
            return False
        if type == SLPacket.TYPE_SLINFT:
            logging.info("Complete INFO:" + self.slconn.getInfoString())
            if self.infolevel is not None:
                return True
            else:
                return False

        # process packet data
        trace = slpack.get_trace()
        if trace is None:
            logging.warning(self.__class__.__name__ + ": blockette contains no trace")
            return False

        # new samples add to the main stream which is then trimmed
        with self.lock:
            # Increment the packet count for the station
            station_id = trace.stats.station
            self.packet_counts[station_id] += 1
            
            # Construct the station ID as expected in the expected_stations set
            full_station_id = f"{trace.stats.network}_{station_id}"
    
            # If the station is in the expected_stations, remove it as it has sent a packet
            self.expected_stations.discard(full_station_id)
            
            # Log the packet count for the station
            logging.info(f"Received packet for station {station_id}, total count: {self.packet_counts[station_id]}")            
            self.stream += trace
            self.stream.merge(-1)
            for tr in self.stream:
                tr.stats.processing = []
        return False
    
    def log_stations_without_packets(self):
        if self.expected_stations:
            logging.info(f"Stations that have not sent a packet: {', '.join(self.expected_stations)}")
        else:
            logging.info("All expected stations have sent packets.")

    def getTraceIDs(self):
        """
        Return a list of SEED style Trace IDs that the SLClient is trying to
        fetch data for.
        """
        ids = []
        streams = self.slconn.get_streams()
        for stream in streams:
            net = stream.net
            sta = stream.station
            selectors = stream.get_selectors()
            for selector in selectors:
                if len(selector) == 3:
                    loc = ""
                else:
                    loc = selector[:2]
                cha = selector[-3:]
                ids.append(".".join((net, sta, loc, cha)))
        ids.sort()
        return ids
           

def _parse_time_with_suffix_to_seconds(timestring):
    """
    Parse a string to seconds as float.

    If string can be directly converted to a float it is interpreted as
    seconds. Otherwise the following suffixes can be appended, case
    insensitive: "s" for seconds, "m" for minutes, "h" for hours, "d" for days.

    >>> _parse_time_with_suffix_to_seconds("12.6")
    12.6
    >>> _parse_time_with_suffix_to_seconds("12.6s")
    12.6
    >>> _parse_time_with_suffix_to_minutes("12.6m")
    756.0
    >>> _parse_time_with_suffix_to_seconds("12.6h")
    45360.0

    :type timestring: str
    :param timestring: "s" for seconds, "m" for minutes, "h" for hours, "d" for
        days.
    :rtype: float
    """
    try:
        return float(timestring)
    except:
        timestring, suffix = timestring[:-1], timestring[-1].lower()
        mult = {'s': 1.0, 'm': 60.0, 'h': 3600.0, 'd': 3600.0 * 24}[suffix]
        return float(timestring) * mult


def _parse_time_with_suffix_to_minutes(timestring):
    """
    Parse a string to minutes as float.

    If string can be directly converted to a float it is interpreted as
    minutes. Otherwise the following suffixes can be appended, case
    insensitive: "s" for seconds, "m" for minutes, "h" for hours, "d" for days.

    >>> _parse_time_with_suffix_to_minutes("12.6")
    12.6
    >>> _parse_time_with_suffix_to_minutes("12.6s")
    0.21
    >>> _parse_time_with_suffix_to_minutes("12.6m")
    12.6
    >>> _parse_time_with_suffix_to_minutes("12.6h")
    756.0

    :type timestring: str
    :param timestring: "s" for seconds, "m" for minutes, "h" for hours, "d" for
        days.
    :rtype: float
    """
    try:
        return float(timestring)
    except:
        seconds = _parse_time_with_suffix_to_seconds(timestring)
    return seconds / 60.0

def print_stream_data(stream):
    # Define this function to print the data from the stream
    for trace in stream:
        trace.normalize()
        print(trace.stats.station)
        print(trace)
        print("="*30)
        
        
def generate_heatmap_data(stream, scnls_data):
    heatmap_data = []
    time_index = []

    for trace in stream:
        # Find the station information in scnls_data
        station_info = next((item for item in scnls_data if item['sta'] == trace.stats.station), None)
        if not station_info:
            continue  # If station info isn't found, skip this trace
              
        lat = station_info['lat']
        lon = station_info['lon']
        data = station_info['data']
        delta = trace.stats.delta  # time between samples
        starttime = trace.stats.starttime.timestamp  # get the UTC timestamp

        for i, intensity in enumerate(data):
            heatmap_data.append([lat, lon, intensity])
            time_index.append(starttime + i * delta)
    
    # Convert heatmap_data into the format expected by HeatMapWithTime, if necessary
    # The expected format is a list of lists, where each sublist represents one time step
    heatmap_series = []
    for t in sorted(set(time_index)):  # Use set to remove duplicates and sort
        time_step_data = [datapoint for j, datapoint in enumerate(heatmap_data) if time_index[j] == t]
        heatmap_series.append(time_step_data)

    # The time_index for HeatMapWithTime should be a list of time steps as strings
    time_index = [str(t) for t in sorted(set(time_index))]

    return heatmap_series, time_index

def create_map(scnls_data, heatmap_series, time_index, file_name='seismic_map.html'):
   
    try:
        print("Creating the map...")
        m = folium.Map(location=[45.5231, -122.6765], zoom_start=6)
        
        # Add the HeatMapWithTime layer
        HeatMapWithTime(heatmap_series, index=time_index).add_to(m)
    
        for station_info in scnls_data:
            lat = station_info['lat']  
            lon = station_info['lon']            
            data_average = station_info.get('data_average', 0) # Use .get() to provide a default value if 'data_average' key is not present
            if data_average == 0:
                print(f"No data_average for station {station_info['key']}.")
            
            # Create a tooltip
            tooltip_text = f"Network: {station_info['net']}<br>"
            tooltip_text += f"Station: {station_info['sta']}<br>"
            tooltip_text += f"Channel: {station_info['chan']}"
                            
            tooltip = folium.Tooltip(tooltip_text, permanent=False, direction='right')

            color = get_color_from_data(data_average)
            
                       
            folium.CircleMarker(
                location=[lat, lon],
                radius=2,
                color=color,
                fill=True,
                fill_color=color,
                tooltip=tooltip  # Add the tooltip to the marker
            ).add_to(m)
    
        m.save(file_name)
        print(f"Map successfully saved to {file_name}")
    except Exception as e:
        print(f"An error occurred while creating the map: {e}")
        logging.error(f"An error occurred while creating the map: {e}")
        
        
    
def get_color_from_data(data_average):
    """
    Converts a list of normalized data to a color.

    The normalized data should be values between -1 and 1.
    This function will convert the average of the values to a color between green and red,
    with green representing -1, red representing 1, and yellow representing 0.

    :param normalized_data: The list of normalized data values between -1 and 1.
    :return: A hexadecimal color string.
    """
    if not data_average:  # Check for empty list
        return '#000000'  # Return black or some default color
    
    # make sure value is within range
    #value = max(min(data_average, 1), -1)
    
    # Linear interpolation between green (0,255,0) for -1, and red (255,0,0) for 1
    if data_average < 0:
        # Color will be between green and yellow
        red = int(255 * (1 + data_average))  # As value goes from -1 to 0, red goes from 0 to 255
        green = 255
    else:
        # Color will be between yellow and red
        red = 255
        green = int(255 * (1 - data_average))  # As value goes from 0 to 1, green goes from 255 to 0
    
    # Blue is always 0
    blue = 0
    
    # Convert to hexadecimal
    color = f'#{red:02X}{green:02X}{blue:02X}'
    
    return color



def main():
    # Configure logging to write to a file, overwriting any existing file.
    logging.basicConfig(filename='GetPNSNstationData.log', filemode='w', level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    

    
    # Your main code here
    logging.info("Program started")
    
    #Ask PNSN quickshake web servide http://quickshake.pnsn.org/scnls for list of active realtime stations, 
    #Create a new JSON file based on the queried data and save locally
    #Iterate through the JSON file to pull out Network, Station and Channel objects to build a list for streaming realtime data from
    #
    if response.status_code == 200:
        json_data = response.json()
        # Save the json data to a local file
        save_SCNLS_json_to_file(json_data, 'scnls_data.json')        
        count = len(json_data)
        print(f"Number of stations: {count}")
        
        # Build the seedlink_streams string from the JSON data
        seedlink_streams = ','.join(f"{info['net']}_{info['sta']}:{info['chan']}" for info in json_data)
        print(f"Seedlink Streams: {seedlink_streams}")
        print("="*30)
        print("Saved SCNLS json to scnls_data.json")
        print("="*30)
    else:
        logging.warning(f"Failed to fetch data: {response.status_code}")
        return
    
    #Seedlink Server to request realtime data from
    seedlink_server = 'rtserve.iris.washington.edu'
    
  
    #now = UTCDateTime()
    stream = Stream()
    lock = threading.Lock()
    
    # seedlink_client initialization and other functions related to seedlink_client
    seedlink_client = SeedlinkUpdater(stream, lock=lock)
    seedlink_client.slconn.set_sl_address(seedlink_server)
    seedlink_client.multiselect = seedlink_streams   
    seedlink_client.initialize()   
    with open('scnls_data.json', 'r') as file: # Load the station data from the JSON file
        scnls_data = json.load(file)
    for station_info in scnls_data:
        station_id = f"{station_info['net']}_{station_info['sta']}" #set a list to determine what stations have not sent a data packet
        seedlink_client.expected_stations.add(station_id)  
        

        
    # start seedlink_client in a thread
    thread = threading.Thread(target=seedlink_client.run)
    #thread.daemon = True
    thread.start()
   
    # run a console-based loop
    try:
        while True:
            #call functions to process and print your data
            with lock:
                if stream:
                    print_stream_data(stream)                 
                    # Update JSON file with incoming stream data
                    update_json_with_trace_data('scnls_data.json', stream)                      
            time.sleep(2)  # Sleep for a bit to avoid a tight loop
        
    except KeyboardInterrupt:
        print("Program interrupted by user, closing connection.")
        seedlink_client.stop_event.set()  # Signal the thread to stop
        thread.join(timeout=30)  # Wait for the thread to finish
        if thread.is_alive():
            print("Thread did not terminate, forcing a shutdown.")
            logging.warning("Thread did not terminate, forcing a shutdown.")
            # Handle the case where the thread did not terminate (e.g., forcefully terminate if necessary)
        else:
            print("Threads successfully stopped.")        
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        seedlink_client.stop_event.set()
        thread.join()                    
    finally:  # Ensure connection is closed on other exceptions
        if hasattr(seedlink_client, 'slconn') and seedlink_client.slconn:
            seedlink_client.slconn.close()
        print("Connection closed.")
        seedlink_client.log_stations_without_packets() #log which stations have not sent data packets
        pass
    
    
    #Open JSON file that has been updated with new data and average_data object and create a simple HTML map
    try:
        with open('scnls_data.json', 'r') as file:
            scnls_data = json.load(file)
        # Now create or update the map with the latest data
        create_map(scnls_data)
    except Exception as e:
        logging.error(f"Error creating map: {e}")



if __name__ == '__main__':
    main()
    logging.shutdown()
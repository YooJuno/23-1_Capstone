///////////////// SERVER /////////////////
///////////////// SERVER /////////////////
///////////////// SERVER /////////////////
///////////////// SERVER /////////////////

#include<iostream>
#include<algorithm>
#include<fstream>
#include<chrono>

// TCP header
#include "opencv4/opencv2/opencv.hpp"
#include <sys/socket.h> 
#include <arpa/inet.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <unistd.h> 
#include <string.h>
#include <pthread.h>

#include<System.h>

#define _WEBCAM_BUILD_

using namespace std;
using namespace cv;

int main(int argc, char **argv)
{
    int sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd == -1) {
        cout << "Failed to create socket." << endl;
        return 1;
    }
    
    sockaddr_in server;
    server.sin_family = AF_INET;
    server.sin_addr.s_addr = INADDR_ANY;
    server.sin_port = htons(atoi(argv[3]));
    
    if (bind(sockfd, (sockaddr*)&server, sizeof(server)) == -1) {
        cout << "Failed to bind socket." << endl;
        return 1;
    }
    
    if (listen(sockfd, 10) == -1) {
        cout << "Failed to listen on socket." << endl;
        return 1;
    }
    
    sockaddr_in client;
    socklen_t clientSize = sizeof(client);
    int clientfd = accept(sockfd, (sockaddr*)&client, &clientSize);
    if (clientfd == -1) {
        cout << "Failed to accept connection." << endl;
        return 1;
    }
    
    ORB_SLAM3::System SLAM(argv[1], argv[2], ORB_SLAM3::System::MONOCULAR, true);
    cout << endl << "-------" << endl;
    


#ifdef COMPILEDWITHC11
    std::chrono::steady_clock::time_point initT = std::chrono::steady_clock::now();
#else
    std::chrono::monotonic_clock::time_point initT = std::chrono::monotonic_clock::now();
#endif

    // Main loop
    while(true)
    {   
        // 이미지 수신
        uint32_t size = 0;
        if (recv(clientfd, &size, sizeof(size), MSG_WAITALL) != sizeof(size)) {
            cout << "Failed to receive size." << endl;
            break;
        }
        
        vector<char> buffer(size);
        if (recv(clientfd, buffer.data(), size, MSG_WAITALL) != size) {
            cout << "Failed to receive data." << endl;
            break;
        }
        // while (send(clientfd, buffer.data(), size, 0) == -1) {
        //     cout << "Failed to send data." << endl;
        //     break;
        // }
        //send(clientfd, buffer.data(), size)

        
        Mat frame = imdecode(buffer, IMREAD_COLOR);
        if (frame.empty()) {
            cout << "Failed to decode image." << endl;
            break;
        }

#ifdef COMPILEDWITHC11
        std::chrono::steady_clock::time_point nowT = std::chrono::steady_clock::now();
#else
        std::chrono::monotonic_clock::time_point nowT = std::chrono::monotonic_clock::now();
#endif

        // Pass the image to the SLAM system
        Sophus::SE3f juno_tcw = SLAM.TrackMonocular(frame, std::chrono::duration_cast<std::chrono::duration<double> >(nowT-initT).count());
    }
        
    SLAM.Shutdown();
    SLAM.SaveKeyFrameTrajectoryTUM("KeyFrameTrajectory.txt");

    return 0;
}
// Headless driver for the SAME Session and HTTPS code used on Vita.
// Protocol on stdin is test-only; this executable is never included in the VPK.
#include "../shared/ui.hpp"
#include <chrono>
#include <iostream>
#include <thread>
int main(int argc,char** argv){
    if(argc!=3)return 2;
    try{
        cv::Session s;s.endpoint=argv[1];s.ca_file=argv[2];
        std::string line;
        while(std::getline(std::cin,line)){
            auto cmd=cv::parse_json(line);auto op=cmd.at("op").str();bool accepted=false;
            if(op=="pair")accepted=s.pair(cmd.at("pin").str());
            else if(op=="project")accepted=s.choose_project(0);
            else if(op=="new")accepted=s.new_thread();
            else if(op=="send"){s.draft=cmd.at("text").str();accepted=s.send();}
            else if(op=="snapshot")accepted=s.refresh();
            else if(op=="stop")accepted=s.interrupt();
            else if(op=="reconcile")accepted=s.reconcile();
            else if(op=="decline"||op=="accept")accepted=s.decide(cmd.at("ticket").str(),op=="accept");
            else if(op=="suspend"){s.suspend();accepted=true;}
            else if(op=="pump")accepted=true;
            else if(op=="quit")break;
            int ticks=cmd.at("ticks").type==cv::Json::Type::Number?std::stoi(cmd.at("ticks").scalar):200;
            ticks=std::clamp(ticks,0,400);
            for(int i=0;i<ticks;++i){s.poll();std::this_thread::sleep_for(std::chrono::milliseconds(5));}
            auto result=cv::Json::obj({{"accepted",cv::Json::boolean(accepted)},{"ready",cv::Json::boolean(s.ready)},
                {"stale",cv::Json::boolean(s.stale)},{"canSend",cv::Json::boolean(s.can_send())},{"notice",cv::Json(s.notice)},
                {"thread",cv::Json(s.thread)},{"projects",cv::Json::list(s.projects)},{"view",s.view}});
            std::cout<<result.dump()<<std::endl;
        }
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}

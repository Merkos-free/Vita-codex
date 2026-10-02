#include "../client/shared/session.hpp"
#include <cassert>
#include <iostream>
#include <functional>

int main(){
    unsigned checks=0;
    auto check=[&](bool b){assert(b);++checks;};
    auto reject=[&](const std::string& text){bool bad=false;try{cv::parse_json(text);}catch(const std::exception&){bad=true;}check(bad);};
    auto j=cv::parse_json("{\"text\":\"Русский \\ud83d\\ude80\",\"list\":[null,true,false,3.14,-2e3]}");
    check(j.at("text").str()=="Русский 🚀");check(j.at("list").array.size()==5);
    check(cv::parse_json(j.dump()).dump()==j.dump());
    for(const auto& bad:{"", "{", "[]x", "{\"x\":1,\"x\":2}", "[1,]", "01", "+1", "1.", "1e", "NaN", "\"\\uD800\"", "\"\\uDC00\"", "\"\\u0000\"", "\"a\nb\"", "true false"})reject(bad);
    reject(std::string(25,'[')+"0"+std::string(25,']'));
    reject("\""+std::string(262145,'x')+"\"");
    reject(std::string(1024*1024+1,' '));
    reject(std::string("\"")+char(0xc0)+char(0x80)+"\"");
    check(cv::valid_endpoint("https://192.168.1.10:8765"));check(cv::valid_endpoint("https://127.0.0.1:443"));
    for(const auto& e:{"http://127.0.0.1:80","https://localhost:443","https://user@127.0.0.1:443","https://127.0.0.1:443/","https://127.1:443","https://01.2.3.4:443","https://256.2.3.4:443","https://224.0.0.1:443","https://127.0.0.1:0","https://127.0.0.1:65536","https://127.0.0.1:443?x"})check(!cv::valid_endpoint(e));
    cv::Session s;check(!s.can_send());check(!s.send());check(!s.interrupt());check(!s.pair("123"));
    check(!s.choose_project(0));check(!s.new_thread());check(!s.resume(0));check(!s.decide("ticket",true));
    s.ready=true;s.stale=false;s.thread="x";s.view=cv::Json::obj({{"status",cv::Json("completed")}});
    check(s.can_send());s.uncertain="old";check(!s.can_send());s.uncertain.clear();s.stale=true;check(!s.can_send());
    s.stale=false;s.view.object["status"]=cv::Json("inProgress");check(!s.can_send());
    s.suspend();check(s.stale);s.disconnect();check(!s.ready&&s.thread.empty());
    std::cout<<checks<<" network model checks passed (host, no device)\n";
}

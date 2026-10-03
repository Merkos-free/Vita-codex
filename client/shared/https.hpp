#pragma once
#include <curl/curl.h>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace cv {
struct Reply {unsigned id=0;long status=0;std::string body,error;bool ok()const{return error.empty()&&status==200;}};
// Literal IPv4 endpoints only: curl_multi_perform never waits on synchronous DNS.
// Both certificate chain AND hostname/IP are verified. No redirects or proxy inheritance.
bool valid_endpoint(const std::string& endpoint);
class Https {
    struct Task;
    CURLM* multi=nullptr;
    std::map<CURL*,std::unique_ptr<Task>> tasks;
public:
    Https();~Https();
    Https(const Https&)=delete;Https& operator=(const Https&)=delete;
    bool start(unsigned id,const std::string& endpoint,const std::string& ca,
               const std::string& path,const std::string& body,const std::string& token="");
    std::vector<Reply> poll();
    void cancel();
    size_t pending()const{return tasks.size();}
};
} // namespace cv

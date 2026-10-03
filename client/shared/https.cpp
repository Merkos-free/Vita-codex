#include "https.hpp"
#include <algorithm>
#include <cctype>
#include <limits>
#include <stdexcept>

namespace cv {
bool valid_endpoint(const std::string& e) {
    if(e.size()>80||e.compare(0,8,"https://")!=0)return false;
    const auto colon=e.find(':',8);if(colon==std::string::npos)return false;
    const auto ip=e.substr(8,colon-8),port=e.substr(colon+1);
    if(port.empty()||port.size()>5)return false;
    unsigned pn=0;for(char c:port){if(c<'0'||c>'9')return false;pn=pn*10+unsigned(c-'0');}if(pn==0||pn>65535)return false;
    size_t start=0;
    for(unsigned i=0;i<4;++i){auto end=ip.find('.',start);if((i==3)!=(end==std::string::npos))return false;
        auto part=ip.substr(start,end==std::string::npos?end:end-start);
        if(part.empty()||part.size()>3||(part.size()>1&&part[0]=='0'))return false;
        unsigned n=0;for(char c:part){if(c<'0'||c>'9')return false;n=n*10+unsigned(c-'0');}if(n>255)return false;
        if(i==0&&(n==0||n>=224))return false;
        start=end==std::string::npos?ip.size():end+1;
    }
    return true;
}
struct Https::Task {
    Reply reply;std::string payload;curl_slist* headers=nullptr;
    ~Task(){curl_slist_free_all(headers);std::fill(payload.begin(),payload.end(),0);}
    static size_t write(char* p,size_t size,size_t count,void* user){
        auto& t=*static_cast<Task*>(user);
        if(size&&count>std::numeric_limits<size_t>::max()/size)return 0;
        size_t n=size*count;if(n>1024*1024-t.reply.body.size())return 0;
        try{t.reply.body.append(p,n);}catch(...){return 0;}return n;
    }
};
Https::Https(){if(curl_global_init(CURL_GLOBAL_DEFAULT)!=CURLE_OK)throw std::runtime_error("curl init failed");multi=curl_multi_init();if(!multi){curl_global_cleanup();throw std::runtime_error("curl multi init failed");}}
Https::~Https(){cancel();curl_multi_cleanup(multi);curl_global_cleanup();}
bool Https::start(unsigned id,const std::string& endpoint,const std::string& ca,const std::string& path,const std::string& body,const std::string& token){
    if(tasks.size()>=3||!valid_endpoint(endpoint)||ca.empty()||ca.size()>512||ca.find('\0')!=std::string::npos||body.empty()||body.size()>32768)return false;
    if(path!="/v1/pair"&&path!="/v1/action")return false;
    if(!token.empty()&&(token.size()<32||token.size()>128||!std::all_of(token.begin(),token.end(),[](unsigned char c){return std::isalnum(c)||c=='_'||c=='-';})))return false;
    auto t=std::make_unique<Task>();t->reply.id=id;t->payload=body;
    t->headers=curl_slist_append(t->headers,"Content-Type: application/json");
    t->headers=curl_slist_append(t->headers,"Expect:");
    if(!token.empty())t->headers=curl_slist_append(t->headers,("Authorization: Bearer "+token).c_str());
    auto* h=curl_easy_init();if(!h)return false;
    CURLcode result=CURLE_OK;
    auto set=[&](CURLoption option,auto value){auto code=curl_easy_setopt(h,option,value);if(code!=CURLE_OK)result=code;};
    set(CURLOPT_URL,(endpoint+path).c_str());set(CURLOPT_CAINFO,ca.c_str());
    set(CURLOPT_SSL_VERIFYPEER,1L);set(CURLOPT_SSL_VERIFYHOST,2L);
    set(CURLOPT_SSLVERSION,long(CURL_SSLVERSION_TLSv1_2));
    set(CURLOPT_FOLLOWLOCATION,0L);set(CURLOPT_MAXREDIRS,0L);set(CURLOPT_PROXY,"");set(CURLOPT_NETRC,long(CURL_NETRC_IGNORED));
#if LIBCURL_VERSION_NUM >= 0x075500
    set(CURLOPT_PROTOCOLS_STR,"https");set(CURLOPT_REDIR_PROTOCOLS_STR,"https");
#else
    set(CURLOPT_PROTOCOLS,long(CURLPROTO_HTTPS));set(CURLOPT_REDIR_PROTOCOLS,long(CURLPROTO_HTTPS));
#endif
    set(CURLOPT_CONNECTTIMEOUT_MS,5000L);set(CURLOPT_TIMEOUT_MS,40000L);set(CURLOPT_NOSIGNAL,1L);
    set(CURLOPT_HTTP_VERSION,long(CURL_HTTP_VERSION_1_1));set(CURLOPT_POST,1L);
    set(CURLOPT_POSTFIELDS,t->payload.c_str());set(CURLOPT_POSTFIELDSIZE,long(t->payload.size()));
    set(CURLOPT_HTTPHEADER,t->headers);set(CURLOPT_WRITEFUNCTION,&Task::write);set(CURLOPT_WRITEDATA,t.get());
    set(CURLOPT_USERAGENT,"CodexVita/0.2");
    if(result!=CURLE_OK||curl_multi_add_handle(multi,h)!=CURLM_OK){curl_easy_cleanup(h);return false;}
    tasks.emplace(h,std::move(t));return true;
}
std::vector<Reply> Https::poll(){
    std::vector<Reply> replies;int running=0;
    if(curl_multi_perform(multi,&running)!=CURLM_OK){for(auto& x:tasks){x.second->reply.error="Network engine failure; outcome unknown";replies.push_back(std::move(x.second->reply));}cancel();return replies;}
    int remaining=0;
    while(auto* msg=curl_multi_info_read(multi,&remaining)){
        if(msg->msg!=CURLMSG_DONE)continue;
        auto it=tasks.find(msg->easy_handle);if(it==tasks.end())continue;
        auto& r=it->second->reply;
        curl_easy_getinfo(msg->easy_handle,CURLINFO_RESPONSE_CODE,&r.status);
        char* content=nullptr;curl_easy_getinfo(msg->easy_handle,CURLINFO_CONTENT_TYPE,&content);
        if(msg->data.result!=CURLE_OK)r.error="TLS/network error ("+std::to_string(int(msg->data.result))+"). No automatic resend.";
        else if(r.status>=300&&r.status<400)r.error="Redirect refused";
        else if(!content||std::string(content).compare(0,16,"application/json")!=0||(content[16]&&content[16]!=';'))r.error="Expected JSON response";
        replies.push_back(std::move(r));curl_multi_remove_handle(multi,msg->easy_handle);curl_easy_cleanup(msg->easy_handle);tasks.erase(it);
    }
    return replies;
}
void Https::cancel(){for(auto& x:tasks){curl_multi_remove_handle(multi,x.first);curl_easy_cleanup(x.first);}tasks.clear();}
} // namespace cv

// Machine-readable test driver; no filesystem access to any patch paths.
#include "../client/shared/diff.hpp"
#include <iostream>
#include <iterator>
int main(){
    std::string input((std::istreambuf_iterator<char>(std::cin)),std::istreambuf_iterator<char>());
    if(input.size()>cv::DiffIndex::MaxBytes)return 2;
    cv::DiffIndex index(input);auto result=cv::Json::list();
    for(const auto& f:index.files)result.array.push_back(cv::Json::obj({
        {"name",cv::Json(f.name)},{"added",cv::Json(std::to_string(f.added))},
        {"removed",cv::Json(std::to_string(f.removed))},{"binary",cv::Json::boolean(f.binary)},
        {"partial",cv::Json::boolean(f.partial)}}));
    std::cout<<result.dump()<<'\n';
}
